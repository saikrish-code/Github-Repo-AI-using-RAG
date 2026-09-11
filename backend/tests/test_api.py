from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

def test_rejects_non_github_repo():
    with TestClient(app) as client:
        email = f"user_{uuid4().hex[:8]}@example.com"
        reg = client.post("/api/v1/auth/register", json={"email": email, "password": "very-secure-pass"})
        token = reg.json()["access_token"]
        response = client.post("/api/v1/repositories", json={"url": "https://example.com/project"}, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 422

def test_auth_and_repo_flow():
    with TestClient(app) as client:
        email = f"user_{uuid4().hex[:8]}@example.com"
        # Register
        reg = client.post("/api/v1/auth/register", json={"email": email, "password": "secure-password-123"})
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        
        # Login
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "secure-password-123"})
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()
        
        # Me
        me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        assert me_res.json()["email"] == email

        # Create valid repository
        repo_res = client.post("/api/v1/repositories", json={"url": "https://github.com/octocat/Hello-World"}, headers={"Authorization": f"Bearer {token}"})
        assert repo_res.status_code == 201
        repo_data = repo_res.json()
        assert repo_data["name"] == "Hello-World"
        repo_id = repo_data["id"]

        # List repositories
        list_res = client.get("/api/v1/repositories", headers={"Authorization": f"Bearer {token}"})
        assert list_res.status_code == 200
        assert any(r["id"] == repo_id for r in list_res.json())

        # Search endpoint
        search_res = client.get(f"/api/v1/repositories/{repo_id}/search?q=Hello", headers={"Authorization": f"Bearer {token}"})
        assert search_res.status_code == 200
