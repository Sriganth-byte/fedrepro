from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

ALGORITHM = "HS256"
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None

