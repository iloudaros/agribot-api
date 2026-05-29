import requests
import datetime
import sys
import api_url 

# Configuration
BASE_URL = api_url.BASE_URL
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

# From seeds-core.sql, Field 45 is owned by testuser
FIELD_ID = 45 

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    print("--- AgriBot PC4 Workflow (Soilless Tomato Monitoring) ---")

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
        "mission_type": "pc4_monitor",
        "start_time": get_iso_now()
    }, headers=headers)
    mission_resp.raise_for_status()
    
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with DB ID: {mission_id}")

    # -----------------------------------------------------
    # 3. UPLOAD PC4 MONITORING DATA
    # -----------------------------------------------------
    print("\n3. Uploading PC4 Monitoring Channels...")
    
    pc4_payload = {
        "parcel_id": FIELD_ID,
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "channels": [
            {
                "channelName": "Channel_A_Row_1",
                "biomass": 2.45,
                "fruitQuality": 0.88,
                "growthInsight": 1.12
            },
            {
                "channelName": "Channel_B_Row_2",
                "biomass": 2.60,
                "fruitQuality": 0.92,
                "growthInsight": 1.15
            },
            {
                "channelName": "Channel_C_Row_3",
                "biomass": 2.10,
                "fruitQuality": 0.81,
                "growthInsight": 0.98
            }
        ]
    }

    pc4_resp = requests.post(f"{BASE_URL}/pc4/missions/{mission_id}/monitor", json=pc4_payload, headers=headers)
    pc4_resp.raise_for_status()
    print(f"✓ {pc4_resp.json()['message']}")

    # -----------------------------------------------------
    # 4. CLOSE OUT BASE MISSION
    # -----------------------------------------------------
    print("\n4. Closing out Base Mission...")
    close_resp = requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers)
    close_resp.raise_for_status()
    print("✓ Base Mission status set to 'complete'.")

    # -----------------------------------------------------
    # 5. VERIFY DATA
    # -----------------------------------------------------
    print("\n5. Fetching Data from API to verify...")
    get_resp = requests.get(f"{BASE_URL}/pc4/missions/{mission_id}/monitor", headers=headers)
    get_resp.raise_for_status()
    
    rows = get_resp.json()
    print(f"✓ Retrieved {len(rows)} monitoring records for Mission {mission_id}:")
    for r in rows:
        print(f"  - Channel: {r['channel_name']:<16} | Biomass: {r['biomass']:.2f} | Quality: {r['fruit_quality']:.2f} | Growth Insight: {r['growth_insight']:.2f}")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
