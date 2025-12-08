import json
from io import BytesIO
from sqlalchemy import select, func, distinct, cast, Float
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import CTE
from typing import Optional
from datetime import datetime, date, time
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, Image, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.units import inch
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.cm as cm

from .models import Log, APIKey
from .schemas import (DashboardResponse, TimeSeriesParam, FilterParams,
                      ReportMetadata, ReportBase, ReportJson, ReportPdf)

EMPTY_DASHBOARD = {
    "summary": {
        "total_requests": 0,
        "unique_ips": 0,
        "avg_response_time": None,
        "min_response_time": None,
        "max_response_time": None,
        "error_rate": 0.0
    },
    "method_usage": {},
    "endpoint_stats": [],
    "status_codes": {},
    "top_ips": [],
    "time_series": []
}


def get_time_series(session: Session, filtered_logs: CTE, period: str) -> list[dict]:
    mapping = {"minutely": '%Y-%m-%d %H:%M',
               "hourly": '%Y-%m-%d %H',
               "daily": '%Y-%m-%d',
               "weekly": '%Y-%W',
               "monthly": '%Y-%m'}

    error_code = filtered_logs.c.status_code.between(400, 599)
    time_series_db = session.execute(
        select(
            func.strftime(mapping[period], filtered_logs.c.created_at).label("timestamp"), # strftime - SQLite-specific
            func.count(filtered_logs.c.id).label("requests"),
            func.avg(filtered_logs.c.process_time).label("avg_time"),
            (cast(func.count().filter(error_code) * 100 / func.count(filtered_logs.c.id),
                  Float)).label('error_rate')
        )
        .group_by(func.strftime(mapping[period], filtered_logs.c.created_at))
        .order_by(func.strftime(mapping[period], filtered_logs.c.created_at).desc())
        .limit(50)
    ).all()

    time_series = [
        {
            "timestamp": ts,
            "requests": req,
            "avg_time": avg,
            "error_rate": rate
        }
        for ts, req, avg, rate in time_series_db
    ]

    return time_series


def get_res_time_stats(session: Session, filtered_logs: CTE) -> dict[str, float]:
    stmt = select(
        func.min(filtered_logs.c.process_time),
        func.avg(filtered_logs.c.process_time),
        func.max(filtered_logs.c.process_time)
    )
    min_time, avg_time, max_time = session.execute(stmt).one()

    if all([min_time, avg_time, max_time]):
        return {
            "min": min_time,
            "avg": avg_time,
            "max": max_time,
        }
    else:
        return {"min": 0, "avg": 0, "max": 0}


def get_unique_ips(session: Session, filtered_logs: CTE) -> int:
    statement = select(func.count(distinct(filtered_logs.c.ip)))
    unique_ips = session.scalar(statement)
    return unique_ips


def get_errors_rate(session: Session, filtered_logs: CTE) -> float:
    errors = session.scalar(
        select(func.count(filtered_logs.c.id))
        .where(filtered_logs.c.status_code.between(400, 599))
    )
    total_requests = get_total_req(session, filtered_logs)
    if total_requests:
        errors_per_100_req = (errors / total_requests) * 100
    else:
        errors_per_100_req = 0
    return errors_per_100_req


def get_method_usage(session: Session, filtered_logs: CTE) -> dict[str, int]:
    method_usage = {
        method: count
        for method, count
        in session.execute(select(filtered_logs.c.method, func.count(filtered_logs.c.id)
                                  ).group_by(filtered_logs.c.method)).all()
    }
    return method_usage


def get_status_codes(session: Session, filtered_logs: CTE) -> dict[str, int]:
    status_codes = {
        status_code: count
        for status_code, count in session.execute(
            select(filtered_logs.c.status_code, func.count(filtered_logs.c.id))
            .group_by(filtered_logs.c.status_code)
        ).all()
    }
    return status_codes


def get_top_ips(session: Session, filtered_logs: CTE) -> list[dict]:
    top_ips_db = session.execute(
        select(filtered_logs.c.ip, func.count(filtered_logs.c.id))
        .group_by(filtered_logs.c.ip)
        .order_by(func.count(filtered_logs.c.id).desc())
        .limit(5)
    ).all()
    top_ips = [{"ip": ip, "requests": requests} for ip, requests in top_ips_db]
    return top_ips


def get_endpoint_stats(session: Session, filtered_logs: CTE) -> list[dict]:
    st_code_cond = filtered_logs.c.status_code.between(400, 599)
    endpoint_stats_db = session.execute(
        select(
            filtered_logs.c.endpoint,
            func.count(filtered_logs.c.id).label("requests"),
            func.avg(filtered_logs.c.process_time).label("avg_time"),
            func.count().filter(st_code_cond).label("error_count")
        )
        .group_by(filtered_logs.c.endpoint)
        .order_by(func.count(filtered_logs.c.id).desc())
        .limit(5)
    ).all()
    endpoint_stats = [
        {
            "endpoint": endpoint,
            "requests": req,
            "avg_time": avg_time,
            "errors_count": errors_count
        }
        for endpoint, req, avg_time, errors_count in endpoint_stats_db
    ]
    return endpoint_stats


def filter_by_time_key(api_key: int, start: date, end: date) -> CTE:
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.max)
    return select(Log).where(Log.api_key_id == api_key
                             ).where(Log.created_at.between(start_dt, end_dt)
                                     ).cte("filtered_logs")


def get_total_req(session: Session, filtered_logs: CTE) -> Optional[int]:
    return session.scalar(select(func.count()).select_from(filtered_logs))


def compute_summary(session: Session, api_key: APIKey, time_series: TimeSeriesParam
                    ) -> DashboardResponse:
    filtered_logs = filter_by_time_key(api_key.id,
                                       time_series.start_date,
                                       time_series.end_date)

    total_requests = get_total_req(session, filtered_logs)

    if not total_requests:
        return DashboardResponse(**EMPTY_DASHBOARD)

    res_time_stats = get_res_time_stats(session, filtered_logs)
    error_rate = get_errors_rate(session, filtered_logs)

    result = {  # type:ignore
        "summary": {
            "total_requests": total_requests,
            "unique_ips": get_unique_ips(session, filtered_logs),
            "avg_response_time": res_time_stats["avg"],
            "min_response_time": res_time_stats["min"],
            "max_response_time": res_time_stats["max"],
            "error_rate": error_rate
        },
        "method_usage": get_method_usage(session, filtered_logs),
        "endpoint_stats": get_endpoint_stats(session, filtered_logs),
        "status_codes": get_status_codes(session, filtered_logs),
        "top_ips": get_top_ips(session, filtered_logs),
        "time_series": get_time_series(session, filtered_logs, time_series.period)
    }
    return DashboardResponse(**result)


def build_log_filters(param: FilterParams, api_key_id: int):  # rewrite in smarter way?
    conditions = [Log.api_key_id == api_key_id]
    if param.start_date:
        start_dt = datetime.combine(param.start_date, time.min)
        conditions.append(Log.created_at >= start_dt)

    if param.end_date:
        end_dt = datetime.combine(param.end_date, time.max)
        conditions.append(Log.created_at <= end_dt)

    if param.method:
        conditions.append(Log.method == param.method)

    if param.status_code:
        conditions.append(Log.status_code == param.status_code)

    if param.endpoint:
        conditions.append(Log.endpoint.contains(param.endpoint))

    if param.ip:
        conditions.append(Log.ip == param.ip)

    if param.process_time_min:
        conditions.append(Log.process_time >= param.process_time_min)

    if param.process_time_max:
        conditions.append(Log.process_time <= param.process_time_max)

    return conditions


def get_report_data(session: Session, api_key: APIKey, time_series: TimeSeriesParam
                    ) -> ReportBase:
    stats = compute_summary(session, api_key, time_series)
    metadata = ReportMetadata(report_name="API Traffic Analysis",
                              generated_at=datetime.now(),
                              period={"start": time_series.start_date,
                                      "end": time_series.end_date})
    return ReportBase(report_metadata=metadata, report=stats)


def build_report_json(report_data: ReportBase) -> bytes:
    report_data_formated = ReportJson(**report_data.model_dump())
    return report_data_formated.model_dump_json(indent=2).encode("utf-8")


def build_report_pdf(report_data: ReportBase) -> bytes:
    report_data_formated = ReportPdf(**report_data.model_dump())
    with BytesIO() as buffer:
        create_pdf_report(buffer, report_data_formated)
        pdf_bytes = buffer.getvalue()
    return pdf_bytes


def create_pie_chart(data, lables):
    buffer = BytesIO()
    plt.style.use('_mpl-gallery-nogrid')
    colors = cm.get_cmap('Blues')(np.linspace(0.2, 0.7, len(data)))
    fig, ax = plt.subplots(dpi=150)
    ax.pie(data, colors=colors, labels=lables, labeldistance=0.7, radius=3,
           center=(4, 4), wedgeprops={"linewidth": 1, "edgecolor": "white"},
           textprops={'fontsize': 7},
           frame=True)

    ax.set_xticks([])
    ax.set_yticks([])
    plt.savefig(buffer, format='jpeg', bbox_inches="tight", dpi=150)
    plt.close()
    buffer.seek(0)
    return buffer


def create_bar_chart(data, labels):
    buffer = BytesIO()
    plt.style.use('_mpl-gallery')
    y = data
    x = labels
    fig, ax = plt.subplots(figsize=(3.2, 3.2), dpi=150)
    ax.bar(x, y, edgecolor="white", linewidth=0.7)
    ax.set_ylabel('requests', fontsize=10)
    plt.xticks(rotation=90, fontsize=10)
    plt.savefig(buffer, format='png', bbox_inches="tight", dpi=150)
    plt.close()
    buffer.seek(0)
    return buffer


def create_two_plots_same_x(bar_data: dict, graph_data, bar_labels,
                            xlabel, ylabel1, ylabel2):
    buffer = BytesIO()
    plt.style.use('_mpl-gallery-nogrid')
    fig, ax1 = plt.subplots(figsize=(14, 6))
    plt.xticks(rotation=90, fontsize=20)
    plt.yticks(fontsize=12)

    ax1.set_xlabel(xlabel, fontsize=20)
    ax1.set_ylabel(ylabel1, fontsize=20)

    bottom = np.zeros(len(bar_labels))

    for boolean, weight_count in bar_data.items():
        p = ax1.bar(bar_labels, weight_count, label=boolean, bottom=bottom)
        bottom += weight_count

    ax1.legend(loc="upper right", fontsize=20)

    ax2 = ax1.twinx()
    color = 'tab:red'

    ax2.set_ylabel(ylabel2, fontsize=20, color=color)
    ax2.tick_params(axis='y', labelsize=20, labelcolor=color)
    ax2.plot(bar_labels, graph_data, color=color)

    fig.tight_layout()

    plt.savefig(buffer, format='png', bbox_inches="tight", dpi=150)
    plt.close()
    buffer.seek(0)
    return buffer


def create_pdf_report(buffer, report_data: ReportPdf):
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20, bottomMargin=20)
    story = []
    title_style = ParagraphStyle(
        'Title',
        parent=getSampleStyleSheet()['Title'],
        textColor=colors.HexColor("#332211"),
    )

    heading_style = ParagraphStyle(
        'Heading',
        parent=getSampleStyleSheet()['Heading1'],
        textColor=colors.HexColor("#332211"),
        alignment=1,
        spaceBefore=5,
        spaceAfter=5
    )
    summary_style = ParagraphStyle(
        'Summary',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#1c2e4a"),
        spaceBefore=5,
        spaceAfter=5
    )
    plot_style = ParagraphStyle(
        'Summary',
        parent=getSampleStyleSheet()['Normal'],
        alignment=1,
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#1c2e4a"),
        spaceBefore=5,
        spaceAfter=5
    )

    title = Paragraph(report_data.report_metadata.report_name, title_style)
    story.append(title)

    generation_date = report_data.report_metadata.generated_at
    period = report_data.report_metadata.period
    meta_data_text = f"""
    <i><b>Generation date:</b> {generation_date}<br/>
    <b>Time period:</b> {period['start']} - {period['end']}</i>
    """
    meta_data = Paragraph(meta_data_text, summary_style)
    story.append(meta_data)

    summary_title = Paragraph("Summary", heading_style)
    story.append(summary_title)

    summary_parts = []
    for k, v in report_data.report.summary.model_dump(by_alias=True).items():
        summary_parts.append(f"{k}: {v}<br/>")
    summary = " ".join(summary_parts)
    story.append(Paragraph(summary, summary_style))

    visuals_title = Paragraph("Visual Data Overview", heading_style)
    story.append(visuals_title)

    methods = []
    methods_data = []
    for k, v in report_data.report.method_usage.items():
        methods.append(k)
        methods_data.append(v)

    status_codes = []
    status_codes_data = []
    for k, v in report_data.report.status_codes.items():
        status_codes.append(k)
        status_codes_data.append(v)

    method_usage = Image(create_pie_chart(methods_data, methods), width=220, height=220)
    status_codes = Image(create_pie_chart(status_codes_data, status_codes), width=220, height=220)
    method_usage_caption = Paragraph("Methods usage", plot_style)
    status_codes_caption = Paragraph("Status codes", plot_style)

    table = Table([
        [method_usage, status_codes],
        [method_usage_caption, status_codes_caption]
    ], hAlign='CENTER')
    story.append(table)

    story.append(Spacer(1, 5))

    ips = []
    ips_data = []
    for dic in report_data.report.top_ips:
        if dic.ip:
            ips.append(dic.ip)
            ips_data.append(dic.requests)

    top_ip = Image(create_bar_chart(ips_data, ips), width=270, height=270)
    top_ip_caption = Paragraph("Top IPs", plot_style)
    story.append(top_ip)
    story.append(top_ip_caption)

    story.append(Spacer(1, 5))

    endpoints = []
    endpoints_data = {"Success": [], "Fails": []}
    response_time = []
    for dic in report_data.report.endpoint_stats:
        endpoints.append(dic.endpoint)
        response_time.append(dic.avg_time)
        endpoints_data["Fails"].append(dic.errors_count)
        endpoints_data["Success"].append(dic.requests - dic.errors_count) # think if None

    endpoints_plot = Image(create_two_plots_same_x(
        endpoints_data, response_time, endpoints,
        'endpoints', 'requests', 'response time avg'
    ), width=430, height=200)
    endpoints_plot_caption = Paragraph("Endpoints statistics", plot_style)
    story.append(endpoints_plot)
    story.append(endpoints_plot_caption)

    story.append(Spacer(1, 5))

    timestamp = []
    time_series_data = {"Success": [], "Fails": []}
    response_time = []
    for dic in report_data.report.time_series:
        timestamp.append(dic.timestamp)
        response_time.append(dic.avg_time)
        fails = dic.error_rate*dic.requests/100
        success = dic.requests - fails
        time_series_data["Fails"].append(fails)
        time_series_data["Success"].append(success)

    time_series_plot = Image(create_two_plots_same_x(
        time_series_data, response_time, timestamp,
        'timestamp', 'requests', 'response time avg'
    ), width=430, height=200)
    time_series_caption = Paragraph("Time series statistics", plot_style)
    story.append(time_series_plot)
    story.append(time_series_caption)

    doc.build(story)
