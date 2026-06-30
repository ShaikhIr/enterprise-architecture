"""Quick test for the countries API."""
import httpx

# Login
login_resp = httpx.post("http://localhost:8000/api/v1/auth/login", json={"username": "admin", "password": "Admin@123!"})
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get regions first
r = httpx.get("http://localhost:8000/api/v1/masters/regions", headers=headers)
regions = r.json()
print(f"Available regions: {regions}")

region_id = regions[0]["id"] if regions else None

# Test list countries (empty)
r = httpx.get("http://localhost:8000/api/v1/masters/countries", headers=headers)
print(f"GET /countries: {r.status_code} → {r.json()}")

# Create a country
payload = {"country_code": "IN", "country_name": "India", "region_id": region_id}
r = httpx.post("http://localhost:8000/api/v1/masters/countries", headers=headers, json=payload)
print(f"POST /countries: {r.status_code} → {r.json()}")

# List again
r = httpx.get("http://localhost:8000/api/v1/masters/countries", headers=headers)
print(f"GET /countries: {r.status_code} → {r.json()}")
