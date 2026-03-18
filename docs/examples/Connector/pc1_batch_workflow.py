import requests
import datetime
import uuid
import time
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser", "password": "supersecretpassword"}

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    print("--- AgriBot PC1 Workflow (Full Lifecycle) ---")

    # -----------------------------------------------------
    # 1. AUTHENTICATE
    # -----------------------------------------------------
    print("\n1. Authenticating...")
    auth_resp = requests.post(f"{BASE_URL}/auth/token", data=AUTH_DATA)
    auth_resp.raise_for_status()
    headers = {
        "Authorization": f"Bearer {auth_resp.json()['access_token']}",
        "Content-Type": "application/json"
    }
    print("✓ Token acquired.")

    # -----------------------------------------------------
    # 2. CREATE BASE MISSION
    # -----------------------------------------------------
    print("\n2. Creating Base Mission...")
    mission_id = str(uuid.uuid4())
    
    requests.post(f"{BASE_URL}/missions", json={
        "id": mission_id,
        "field_id": 1,
        "mission_type": "pc1_inspection_and_spraying",
        "start_time": get_iso_now()
    }, headers=headers).raise_for_status()
    
    print(f"✓ Base Mission created: {mission_id}")

    # Set PC1 State to ONGOING
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "ongoing"
    }, headers=headers).raise_for_status()
    print("✓ PC1 State set to: ongoing")

    # -----------------------------------------------------
    # 3. PHASE 1: INSPECTION (BATCH UPLOAD WEEDS)
    # -----------------------------------------------------
    print("\n3. Phase 1: BATCH Uploading Detected Weeds (Inspection)...")
    
    # The UGV/Connector now generates its own IDs for the weeds
    weed_id_1 = str(uuid.uuid4())
    weed_id_2 = str(uuid.uuid4())

    weeds_payload = [
        {
            "id": weed_id_1,
            "inspection_id": mission_id,
            "name": "weeds_01.png",
            "image": "minio://agribot-mission-images/pc1/weeds_01.png",
            "confidence": 0.85,
            "latitude": 38.2915,
            "longitude": 23.3732,
            "is_sprayed": False
        },
        {
            "id": weed_id_2,
            "inspection_id": mission_id,
            "name": "weeds_02.png",
            "image": "minio://agribot-mission-images/pc1/weeds_02.png",
            "confidence": 0.92,
            "latitude": 38.2916,
            "longitude": 23.3733,
            "is_sprayed": False
        }
    ]

    requests.post(f"{BASE_URL}/pc1/weeds/batch", json=weeds_payload, headers=headers).raise_for_status()
    print(f"✓ Successfully uploaded {len(weeds_payload)} weeds.")

    # Update PC1 State to INSPECTION_COMPLETE
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "inspection_complete"
    }, headers=headers).raise_for_status()
    print("✓ PC1 State set to: inspection_complete")

    # Simulate time passing between inspection and spraying
    print("\n   ... Waiting for UGV to perform spraying pass ...")
    time.sleep(2)

    # -----------------------------------------------------
    # 4. PHASE 2: SPRAYING (BATCH UPDATE WEEDS)
    # -----------------------------------------------------
    print("\n4. Phase 2: BATCH Updating Weeds as Sprayed...")
    spray_time = get_iso_now()
    
    # Because of the composite primary key, we MUST provide both 'id' and 'inspection_id'
    update_payload = [
        {"id": weed_id_1, "inspection_id": mission_id, "is_sprayed": True, "spray_time": spray_time},
        {"id": weed_id_2, "inspection_id": mission_id, "is_sprayed": True, "spray_time": spray_time}
    ]
    
    requests.patch(f"{BASE_URL}/pc1/weeds/batch", json=update_payload, headers=headers).raise_for_status()
    print(f"✓ Successfully marked {len(update_payload)} weeds as sprayed.")

    # Update PC1 State to SPRAYING_COMPLETE
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "spraying_complete"
    }, headers=headers).raise_for_status()
    print("✓ PC1 State set to: spraying_complete")

    # -----------------------------------------------------
    # 5. CLOSE OUT BASE MISSION
    # -----------------------------------------------------
    print("\n5. Closing out Base Mission...")
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()
    print("✓ Base Mission status set to complete with end_time.")

    # -----------------------------------------------------
    # 6. VERIFY DATA
    # -----------------------------------------------------
    print("\n6. Fetching final data to verify...")
    get_weeds_resp = requests.get(f"{BASE_URL}/pc1/weeds/{mission_id}", headers=headers)
    get_weeds_resp.raise_for_status()
    
    weeds_data = get_weeds_resp.json()
    for w in weeds_data:
         status = "✅ Sprayed" if w['is_sprayed'] else "❌ Not Sprayed"
         print(f"  - Weed ID: {w['id'].split('-')[0]}... | Conf: {w['confidence']*100}% | Status: {status} at {w['spray_time']}")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            # This prints the exact validation error or SQL error from FastAPI
            print(f"Server replied: {e.response.text}")
