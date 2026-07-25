from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    commit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class CodeChunk(Base):
    __tablename__ = "code_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    branch: Mapped[str] = mapped_column(String(255), default="main")
    path: Mapped[str] = mapped_column(String(2048), index=True)
    language: Mapped[str] = mapped_column(String(64), index=True)
    symbol_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    symbol_kind: Mapped[str] = mapped_column(String(64), default="module")
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    imports: Mapped[list] = mapped_column(JSON, default=list)
    exports: Mapped[list] = mapped_column(JSON, default=list)
    commit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_version: Mapped[str] = mapped_column(String(64), default="v1")
