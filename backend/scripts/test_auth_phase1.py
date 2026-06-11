"""Quick smoke test for Phase 1 auth. Run: python scripts/test_auth_phase1.py"""
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.services.seed import seed_super_admin

db = SessionLocal()
seed_super_admin(db)
db.close()

client = TestClient(app)

r = client.post("/api/v1/auth/login", json={"email": "admin@vibration.com", "password": "Admin@2024"})
print("LOGIN", r.status_code)
assert r.status_code == 200, r.text
tokens = r.json()
print("  expires_in:", tokens["expires_in"])

r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
print("ME", r2.status_code, r2.json())
assert r2.status_code == 200
assert "super_admin" in r2.json()["roles"]

r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
print("REFRESH", r3.status_code)
assert r3.status_code == 200

r4 = client.post("/api/v1/auth/logout", json={"refresh_token": r3.json()["refresh_token"]})
print("LOGOUT", r4.status_code)
assert r4.status_code == 204

r5 = client.get("/api/v1/auth/me")
print("ME_NO_AUTH", r5.status_code)
assert r5.status_code == 401

print("ALL TESTS PASSED")
