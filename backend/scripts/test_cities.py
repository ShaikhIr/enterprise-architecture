import httpx

login_resp = httpx.post("http://localhost:8000/api/v1/auth/login", json={"username": "admin", "password": "Admin@123!"})
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get states
r = httpx.get("http://localhost:8000/api/v1/masters/states", headers=headers)
states = r.json()
state_id = states[0]["id"] if states else None
print(f"Using state: {states[0]['state_name'] if states else 'none'}")

# List cities
r = httpx.get("http://localhost:8000/api/v1/masters/cities", headers=headers)
print(f"GET /cities: {r.status_code} → {r.json()}")

# Create city
if state_id:
    r = httpx.post("http://localhost:8000/api/v1/masters/cities", headers=headers, json={"state_id": state_id, "city_name": "Mumbai"})
    print(f"POST /cities: {r.status_code} → {r.json()}")
