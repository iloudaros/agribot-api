# This script demonstrates a complete workflow for the PC1 use case, 
# where a UGV performs an inspection pass to detect weeds and then later performs a spraying pass to spray those weeds. 
# The script interacts with the API to create missions, upload detected weeds, and update their status after spraying.
# It is intended to be used by the Connector to push data to the database as part of the PC1 use case.

import requests
import datetime
import uuid
import time
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser", "password": "testpassword"}

def main():
    print("--- AgriBot PC1 Workflow (Inspection & Spraying) ---")

    # 1. Authenticate
    print("\n1. Authenticating...")
    auth_resp = requests.post(f"{BASE_URL}/auth/token", data=AUTH_DATA)
    if auth_resp.status_code != 200:
        print(f"Auth Failed: {auth_resp.text}")
        sys.exit(1)
        
    headers = {
        "Authorization": f"Bearer {auth_resp.json()['access_token']}",
        "Content-Type": "application/json"
    }

    # 2. Create the PC1 Mission
    print("\n2. Creating PC1 Inspection Mission...")
    mission_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    mission_payload = {
        "id": mission_id,
        "field_id": 1,
        "mission_type": "pc1_inspection",
        "status": "complete",
        "start_time": now,
        "mission_date": now
    }
    requests.post(f"{BASE_URL}/pc1/missions", json=mission_payload, headers=headers).raise_for_status()
    print(f"✓ Mission created with ID: {mission_id}")

    # 3. PHASE 1: Upload Detected Weeds (NOT SPRAYED YET)
    print("\n3. Phase 1: Uploading Detected Weeds (is_sprayed = False)...")
    weeds_payloads = [
        {
            "inspection_id": mission_id,
            "name": "weeds_01.png",
            "image": "minio://agribot-mission-images/pc1/weeds_01.png",
            "confidence": 0.85,
            "latitude": 38.2915,
            "longitude": 23.3732,
            "is_sprayed": False # Default state
        },
        {
            "inspection_id": mission_id,
            "name": "weeds_02.png",
            "image": "minio://agribot-mission-images/pc1/weeds_02.png",
            "confidence": 0.92,
            "latitude": 38.2916,
            "longitude": 23.3733,
            "is_sprayed": False # Default state
        }
    ]

    uploaded_weed_ids = []
    for weed in weeds_payloads:
        weed_resp = requests.post(f"{BASE_URL}/pc1/weeds", json=weed, headers=headers)
        weed_resp.raise_for_status()
        weed_id = weed_resp.json()['id']
        uploaded_weed_ids.append(weed_id)
        print(f"  ✓ Weed uploaded! DB ID: {weed_id}")

    # SIMULATE TIME PASSING (e.g., UGV goes back out the next day)
    print("\n   ... Waiting for UGV to perform spraying pass ...")
    time.sleep(2)

    # 4. PHASE 2: Update Weeds as Sprayed
    print("\n4. Phase 2: Updating Weeds as Sprayed...")
    spray_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    for w_id in uploaded_weed_ids:
        update_payload = {
            "is_sprayed": True,
            "spray_time": spray_time
        }
        update_resp = requests.patch(f"{BASE_URL}/pc1/weeds/{w_id}", json=update_payload, headers=headers)
        update_resp.raise_for_status()
        print(f"  ✓ Weed {w_id} updated! is_sprayed=True")


    # 5. Fetch the Data to verify
    print("\n5. Fetching Data from API to verify...")
    get_weeds_resp = requests.get(f"{BASE_URL}/pc1/weeds/{mission_id}", headers=headers)
    get_weeds_resp.raise_for_status()
    
    weeds_data = get_weeds_resp.json()
    for w in weeds_data:
         status = "✅ Sprayed" if w['is_sprayed'] else "❌ Not Sprayed"
         print(f"  - ID: {w['id']} | Conf: {w['confidence']*100}% | Status: {status} at {w['spray_time']}")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
