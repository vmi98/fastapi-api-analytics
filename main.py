from fastapi import FastAPI
from contextlib import asynccontextmanager
from server.routers import router
from server.models import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(router)


@app.get("/")
def root():
    return {"msg": "Analytics service OK"}
