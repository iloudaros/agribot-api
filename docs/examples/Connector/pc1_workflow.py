# This script demonstrates a complete workflow for the PC1 use case, 
# where a UGV performs an inspection pass to detect weeds and then later performs a spraying pass to spray those weeds. 
# The script interacts with the API to create missions, upload detected weeds (one by one), and update their status after spraying.

import requests
import datetime
import uuid
import time
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser", "password": "supersecretpassword"} # Fixed password

def get_iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    print("--- AgriBot PC1 Workflow (Single Item Uploads) ---")

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

    # 2. Create the Generic Mission
    print("\n2. Creating Generic Mission...")
    mission_id = str(uuid.uuid4())
    
    mission_payload = {
        "id": mission_id,
        "field_id": 1,
        "mission_type": "pc1_inspection",
        "start_time": get_iso_now()
    }
    requests.post(f"{BASE_URL}/missions", json=mission_payload, headers=headers).raise_for_status()
    print(f"✓ Mission created with ID: {mission_id}")

    # Set initial PC1 state
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "ongoing"
    }, headers=headers).raise_for_status()

    # 3. PHASE 1: Upload Detected Weeds (NOT SPRAYED YET)
    print("\n3. Phase 1: Uploading Detected Weeds individually...")
    
    # UGV generates IDs now!
    weeds_payloads = [
        {
            "id": str(uuid.uuid4()), # <--- NEW: Explicit ID
            "inspection_id": mission_id,
            "name": "weeds_01.png",
            "image": "minio://agribot-mission-images/pc1/weeds_01.png",
            "confidence": 0.85,
            "latitude": 38.2915,
            "longitude": 23.3732,
            "is_sprayed": False 
        },
        {
            "id": str(uuid.uuid4()), # <--- NEW: Explicit ID
            "inspection_id": mission_id,
            "name": "weeds_02.png",
            "image": "minio://agribot-mission-images/pc1/weeds_02.png",
            "confidence": 0.92,
            "latitude": 38.2916,
            "longitude": 23.3733,
            "is_sprayed": False 
        }
    ]

    uploaded_weed_ids = []
    # Send one request per weed
    for weed in weeds_payloads:
        weed_resp = requests.post(f"{BASE_URL}/pc1/weeds", json=weed, headers=headers)
        weed_resp.raise_for_status()
        
        # Grab the string ID returned by the API
        weed_id = weed_resp.json()['id']
        uploaded_weed_ids.append(weed_id)
        print(f"  ✓ Weed uploaded! DB ID: {weed_id}")

    # Mark Inspection Complete
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "inspection_complete"
    }, headers=headers).raise_for_status()

    # SIMULATE TIME PASSING 
    print("\n   ... Waiting for UGV to perform spraying pass ...")
    time.sleep(2)

    # 4. PHASE 2: Update Weeds as Sprayed
    print("\n4. Phase 2: Updating Weeds individually as Sprayed...")
    spray_time = get_iso_now()
    
    for w_id in uploaded_weed_ids:
        update_payload = {
            "is_sprayed": True,
            "spray_time": spray_time
        }
        # Note: If your backend PATCH endpoint requires inspection_id due to the composite key, 
        # add "inspection_id": mission_id to the payload above.
        update_resp = requests.patch(f"{BASE_URL}/pc1/weeds/{w_id}", json=update_payload, headers=headers)
        update_resp.raise_for_status()
        print(f"  ✓ Weed {w_id} updated! is_sprayed=True")

    # Mark Spraying Complete & Close Mission
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "spraying_complete"
    }, headers=headers).raise_for_status()
    
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()

    # 5. Fetch the Data to verify
    print("\n5. Fetching Data from API to verify...")
    get_weeds_resp = requests.get(f"{BASE_URL}/pc1/weeds/{mission_id}", headers=headers)
    get_weeds_resp.raise_for_status()
    
    weeds_data = get_weeds_resp.json()
    for w in weeds_data:
         status = "✅ Sprayed" if w['is_sprayed'] else "❌ Not Sprayed"
         # Slicing the UUID just to make the console output cleaner
         print(f"  - ID: {w['id'][:8]}... | Conf: {w['confidence']*100}% | Status: {status} at {w['spray_time']}")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
