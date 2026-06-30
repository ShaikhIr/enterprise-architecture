import httpx

# Login
login_resp = httpx.post("http://localhost:8000/api/v1/auth/login", json={"username": "admin", "password": "Admin@123!"})
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Test template download
r = httpx.get("http://localhost:8000/api/v1/masters/regions-template", headers=headers)
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('content-type')}")
print(f"Content-Disposition: {r.headers.get('content-disposition')}")
print(f"Body length: {len(r.content)} bytes")
