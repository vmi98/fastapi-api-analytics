from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.auth import auth_router
from server.models import create_db_and_tables
from server.routers import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(router)
app.include_router(auth_router)


@app.get("/")
def root():
    return {"msg": "Analytics service OK"}
