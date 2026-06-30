"""Quick test for the regions API."""
import httpx

# Login to get a fresh token
login_resp = httpx.post("http://localhost:8000/api/v1/auth/login", json={"username": "admin", "password": "Admin@123!"})
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Test list regions
r = httpx.get("http://localhost:8000/api/v1/masters/regions", headers=headers)
print(f"GET /regions: {r.status_code} → {r.json()}")

# Test create region
r = httpx.post("http://localhost:8000/api/v1/masters/regions", headers=headers, json={"region_name": "Asia Pacific", "region_id": "APAC"})
print(f"POST /regions: {r.status_code} → {r.json()}")

# List again
r = httpx.get("http://localhost:8000/api/v1/masters/regions", headers=headers)
print(f"GET /regions: {r.status_code} → {r.json()}")
