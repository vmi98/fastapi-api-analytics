import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    status,
)
from sqlmodel import select

from .models import APIKey, SessionDep


MAX_API_KEY_LEN = 64

def generate_api_key() -> str:
    return str(uuid.uuid4())


def get_api_key(session: SessionDep,
                api_key: Optional[str] = Header(None, alias="X-API-Key"),
                ) -> APIKey:
    if not api_key or len(api_key) > MAX_API_KEY_LEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
        )

    key_obj = session.exec(
        select(APIKey).where(APIKey.api_key == api_key)
    ).first()

    if not key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return key_obj


auth_router = APIRouter()


@auth_router.post("/generate_key", response_model=str)
def generate_key_route(session: SessionDep) -> str:
    key = generate_api_key()
    session.add(APIKey(api_key=key))
    session.commit()
    return key
