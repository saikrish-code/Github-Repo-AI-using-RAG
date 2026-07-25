from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, HttpUrl

class RegisterRequest(BaseModel): email: EmailStr; password: str = Field(min_length=10, max_length=128)
class LoginRequest(RegisterRequest): pass
class TokenResponse(BaseModel): access_token: str; token_type: str = "bearer"
class RepoCreate(BaseModel): url: HttpUrl; branch: str | None = None
class RepoOut(BaseModel): id: str; url: str; name: str; default_branch: str; status: str; stats: dict; created_at: datetime
class ChatRequest(BaseModel): question: str = Field(min_length=2, max_length=4000); branch: str | None = None
class Citation(BaseModel): path: str; start_line: int; end_line: int; symbol: str | None = None
class SearchResult(BaseModel): content: str; citation: Citation; score: float
