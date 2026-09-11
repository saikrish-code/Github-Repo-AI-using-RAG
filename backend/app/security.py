from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from sqlalchemy.orm import Session
from .core import settings
from .db import get_db
from .models import User

bearer = HTTPBearer()
def hash_password(password: str) -> str:
    pw_bytes = password[:72].encode("utf-8")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        pw_bytes = password[:72].encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))
    except Exception:
        return False

def create_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, settings().jwt_secret, algorithm="HS256")
def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try: user_id = jwt.decode(credentials.credentials, settings().jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token")
    user = db.get(User, user_id)
    if not user: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user
