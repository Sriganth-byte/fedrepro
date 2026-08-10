from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import User
from app.schemas.contracts import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(name=payload.name.strip(), email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenResponse(access_token=create_access_token(user.id))

