import os
from dotenv import load_dotenv
import httpx
from time import perf_counter
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint


load_dotenv()
API_BASE = os.environ.get('API_BASE')


async def send_log(log: dict, api_key: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{API_BASE}/track",
                              json=log,
                              headers={'X-API-Key': api_key})
    except Exception:
        pass


def create_tracking_middleware(api_key: str):
    async def tracking_middleware(request: Request,
                                  call_next: RequestResponseEndpoint
                                  ) -> Response:
        start_time = perf_counter()

        response = await call_next(request)

        log = {'created_at': datetime.now().isoformat(),
               'method': request.method,
               'endpoint': request.url.path,
               'ip': request.client.host if request.client else None,
               'process_time': (perf_counter() - start_time) * 1000,
               'status_code': response.status_code
               }
        await send_log(log, api_key)
        return response
    return tracking_middleware
