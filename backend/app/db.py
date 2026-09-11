from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .core import settings

DB_FILE = Path(__file__).resolve().parent.parent / "reposage.db"

def _get_engine():
    db_url = settings().database_url
    try:
        eng = create_engine(db_url, pool_pre_ping=True)
        with eng.connect(): pass
        return eng
    except Exception:
        return create_engine(f"sqlite:///{DB_FILE.as_posix()}", connect_args={"check_same_thread": False})

engine = _get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
class Base(DeclarativeBase): pass
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
