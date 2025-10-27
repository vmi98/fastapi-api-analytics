import uuid
import os
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from typing import Optional, Annotated

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    status,
)

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from pwdlib import PasswordHash

from .models import APIKey, User, SessionDep
from .schemas import Token, TokenData, UserOutput, UserInDB, RegisterForm


load_dotenv()

MAX_API_KEY_LEN = 64

SECRET_KEY = os.environ.get('SECRET_KEY')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 90

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)


def get_user(session: SessionDep, username: str):
    user = session.execute(select(User).where(User.username == username)).scalars().first()

    if user:
        return UserInDB.model_validate(user)
    return None


def authenticate_user(session: SessionDep, username: str, password: str):
    user = get_user(session, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)],
                     session: SessionDep):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(session, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


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

    key_obj = session.scalars(select(APIKey).where(APIKey.api_key == api_key)).first()

    if not key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return key_obj


auth_router = APIRouter()


@auth_router.post("/generate_key", response_model=str)
def generate_key_route(session: SessionDep, user: UserInDB = Depends(get_current_user)
                       ) -> str:
    key = generate_api_key()
    session.add(APIKey(api_key=key, user_id=user.id))
    session.commit()
    return key


@auth_router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@auth_router.get("/me/", response_model=UserOutput)
def read_me(
    current_user: Annotated[UserOutput, Depends(get_current_user)]
) -> UserOutput:
    return current_user


@auth_router.post("/register", response_model=UserOutput)
def register_user(session: SessionDep, form_data: RegisterForm
                  ) -> UserOutput:
    username = form_data.username
    hashed_password = get_password_hash(form_data.password)
    if get_user(session, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    user = User(username=username, hashed_password=hashed_password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
