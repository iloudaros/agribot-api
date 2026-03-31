import requests
import datetime
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

# Note: In your AgroApps example, you used parcel_id 45. 
# Make sure your seeds-core.sql has a field with id=45 owned by testuser!
FIELD_ID = 45 

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    print("--- AgriBot PC3 Workflow (Batch Telemetry Upload & Webhook) ---")

    # -----------------------------------------------------
    # 1. AUTHENTICATE
    # -----------------------------------------------------
    print("\n1. Authenticating...")
    auth_resp = requests.post(f"{BASE_URL}/auth/token", data=AUTH_DATA)
    if auth_resp.status_code != 200:
        print(f"Auth Failed: {auth_resp.text}")
        sys.exit(1)
        
    headers = {
        "Authorization": f"Bearer {auth_resp.json()['access_token']}",
        "Content-Type": "application/json"
    }
    print("✓ Token acquired.")

    # -----------------------------------------------------
    # 2. CREATE BASE MISSION
    # -----------------------------------------------------
    print("\n2. Creating Base Mission...")
    
    mission_resp = requests.post(f"{BASE_URL}/missions", json={
        "field_id": FIELD_ID, 
        "mission_type": "pc3_inspection",
        "start_time": get_iso_now()
    }, headers=headers)
    mission_resp.raise_for_status()
    
    # Extract the auto-generated INT ID from the database response
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with DB ID: {mission_id}")

    # -----------------------------------------------------
    # 3. UPLOAD CSV TELEMETRY (BATCH)
    # -----------------------------------------------------
    print("\n3. Batch Uploading PC3 Telemetry...")
    
    # Simulating data parsed from: 20250513_121239_N1II_IntelRealSenseD435_SN838212073089.csv
    # Notice we now include the required 'timestamp_unix' field
    telemetry_payload = {
        "mission_id": mission_id,
        "data": [
            {
                "timestamp_unix": 1747131248.99966,
                "latitude": 41.1398829,
                "longitude": 16.798385,
                "altitude_m": 55.396,
                "avg_dim_x_cm": 37.809142435232,
                "avg_dim_y_cm": 31.0884559023066,
                "avg_dim_z_cm": 19.0,
                "avg_volume_cm3": 22333.1292887331,
                "avg_fol_area_cm2": 603.197958145333,
                "avg_ndvi": 0.701093289426946,
                "avg_biomass": 1.0,
                "avg_fertilization": 0.5
            },
            {
                "timestamp_unix": 1747131249.99966,
                "latitude": 41.1398828,
                "longitude": 16.7983851,
                "altitude_m": 55.402,
                "avg_dim_x_cm": 22.3728752705451,
                "avg_dim_y_cm": 22.8499321573948,
                "avg_dim_z_cm": 21.2333333333333,
                "avg_volume_cm3": 16976.7464097236,
                "avg_fol_area_cm2": 277.713955864568,
                "avg_ndvi": 0.701690146235136,
                "avg_biomass": 1.0,
                "avg_fertilization": 0.5
            },
            {
                "timestamp_unix": 1747131250.99966,
                "latitude": 41.1398829,
                "longitude": 16.7983850,
                "altitude_m": 55.398,
                "avg_dim_x_cm": 18.4170427153684,
                "avg_dim_y_cm": 25.1821329715061,
                "avg_dim_z_cm": 17.500,
                "avg_volume_cm3": 8116.15732550552,
                "avg_fol_area_cm2": 218.152309882628,
                "avg_ndvi": 0.58218638168167,
                "avg_biomass": 1.0,
                "avg_fertilization": 0.5
            }
        ]
    }

    pc3_resp = requests.post(f"{BASE_URL}/pc3/inspections/batch", json=telemetry_payload, headers=headers)
    pc3_resp.raise_for_status()
    print(f"✓ {pc3_resp.json()['message']}")

    # -----------------------------------------------------
    # 4. CLOSE OUT BASE MISSION (Triggers AgroApps Webhook!)
    # -----------------------------------------------------
    print("\n4. Closing out Base Mission...")
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()
    print("✓ Base Mission status set to complete (AgroApps webhook triggered!)")

    # -----------------------------------------------------
    # 5. VERIFY DATA
    # -----------------------------------------------------
    print("\n5. Fetching Data from API to verify...")
    get_resp = requests.get(f"{BASE_URL}/pc3/inspections/{mission_id}", headers=headers)
    get_resp.raise_for_status()
    
    rows = get_resp.json()
    print(f"✓ Retrieved {len(rows)} telemetry rows for Mission {mission_id}:")
    for r in rows:
         print(f"  - Timestamp: {r.get('timestamp_unix', 'N/A')} | NDVI: {r['avg_ndvi']} | Vol: {r['avg_volume_cm3']}cm3 | Pos: {r['latitude']},{r['longitude']}")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
