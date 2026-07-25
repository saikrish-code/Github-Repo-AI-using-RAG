from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

def test_rejects_non_github_repo():
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/register", json={"email":"a@example.com", "password":"very-secure-pass"}).json()["access_token"]
        response = client.post("/api/v1/repositories", json={"url":"https://example.com/project"}, headers={"Authorization":f"Bearer {token}"})
        assert response.status_code == 422
