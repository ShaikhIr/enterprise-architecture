import httpx

login_resp = httpx.post("http://localhost:8000/api/v1/auth/login", json={"username": "admin", "password": "Admin@123!"})
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get countries
r = httpx.get("http://localhost:8000/api/v1/masters/countries", headers=headers)
countries = r.json()
country_id = countries[0]["id"] if countries else None
print(f"Using country: {countries[0]['country_name'] if countries else 'none'}")

# List states
r = httpx.get("http://localhost:8000/api/v1/masters/states", headers=headers)
print(f"GET /states: {r.status_code} → {r.json()}")

# Create state
if country_id:
    r = httpx.post("http://localhost:8000/api/v1/masters/states", headers=headers, json={"country_id": country_id, "language_key": "EN", "state_name": "Maharashtra"})
    print(f"POST /states: {r.status_code} → {r.json()}")
