import requests
import datetime
import time
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    print("--- AgriBot PC1 Workflow (Weed Inspection & Spraying) ---")

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
        "field_id": 44,
        "mission_type": "pc1_inspection_and_spraying",
        "start_time": get_iso_now()
    }, headers=headers)
    mission_resp.raise_for_status()
    
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with auto-generated DB ID: {mission_id}")

    # Set PC1 State to ONGOING
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "ongoing"
    }, headers=headers).raise_for_status()
    print("✓ PC1 State set to: ongoing")

    # -----------------------------------------------------
    # 3. PHASE 1: UPLOAD IMAGES TO MINIO
    # -----------------------------------------------------
    print("\n3. Phase 1a: Requesting secure links & uploading images to MinIO...")
    
    # Weeds data detected by the robot (missing 'image' URI for now)
    detected_weeds = [
        {
            "id": 1,  
            "inspection_id": mission_id,
            "name": "weeds_01.jpg",
            "confidence": 0.85,
            "latitude": 38.2915,
            "longitude": 23.3732,
            "needs_verification": True,
            "is_sprayed": False
        },
        {
            "id": 2, 
            "inspection_id": mission_id,
            "name": "weeds_02.jpg",
            "confidence": 0.92,
            "latitude": 38.2916,
            "longitude": 23.3733,
            "needs_verification": False,
            "is_sprayed": False
        }
    ]

    for weed in detected_weeds:
        # A. Request Presigned URL from FastAPI
        presigned_req = requests.post(f"{BASE_URL}/pc1/images/presigned-url", json={
            "filename": weed["name"],
            "inspection_id": mission_id
        }, headers=headers)
        presigned_req.raise_for_status()
        
        minio_data = presigned_req.json()
        upload_url = minio_data["upload_url"]
        image_uri = minio_data["image_uri"]
        
        # B. Upload the actual image file to MinIO (Bypassing FastAPI)
        # Using dummy bytes here to simulate an image file
        dummy_image_bytes = b"fake_image_data_from_camera"
        upload_resp = requests.put(upload_url, data=dummy_image_bytes)
        upload_resp.raise_for_status()
        
        # C. Attach the generated URI to our weed payload
        weed["image"] = image_uri
        print(f"  ✓ Uploaded {weed['name']} -> {image_uri}")

    # -----------------------------------------------------
    # 4. PHASE 1: INSPECTION (BATCH UPLOAD WEEDS TO DB)
    # -----------------------------------------------------
    print("\n4. Phase 1b: BATCH Uploading Detected Weeds to Database...")
    requests.post(f"{BASE_URL}/pc1/weeds/batch", json=detected_weeds, headers=headers).raise_for_status()
    print(f"✓ Successfully saved {len(detected_weeds)} weeds to the database.")

    # Update PC1 State to INSPECTION_COMPLETE (Triggers the AgroApps Webhook!)
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "inspection_complete"
    }, headers=headers).raise_for_status()
    print("✓ PC1 State set to: inspection_complete (AgroApps webhook triggered!)")

    # Simulate time passing between inspection and spraying
    print("\n   ... Waiting for UGV to perform spraying pass ...")
    time.sleep(2)

    # -----------------------------------------------------
    # 5. PHASE 2: SPRAYING (BATCH UPDATE WEEDS)
    # -----------------------------------------------------
    print("\n5. Phase 2: BATCH Updating Weeds as Sprayed...")
    spray_time = get_iso_now()
    
    # Send the update targeting the integers
    update_payload = [
        {"id": 1, "inspection_id": mission_id,"verified": True, "is_sprayed": True, "spray_time": spray_time},
        {"id": 2, "inspection_id": mission_id, "is_sprayed": True, "spray_time": spray_time}
    ]
    
    requests.patch(f"{BASE_URL}/pc1/weeds/batch", json=update_payload, headers=headers).raise_for_status()
    print(f"✓ Successfully marked {len(update_payload)} weeds as sprayed.")

    # Update PC1 State to SPRAYING_COMPLETE (Triggers the 2nd AgroApps Webhook!)
    requests.put(f"{BASE_URL}/pc1/missions/{mission_id}/state", json={
        "mission_id": mission_id,
        "status": "spraying_complete"
    }, headers=headers).raise_for_status()
    print("✓ PC1 State set to: spraying_complete (AgroApps webhook triggered!)")

    # -----------------------------------------------------
    # 6. CLOSE OUT BASE MISSION
    # -----------------------------------------------------
    print("\n6. Closing out Base Mission...")
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()
    print("✓ Base Mission status set to complete with end_time.")

    # -----------------------------------------------------
    # 7. VERIFY DATA & TEST GET IMAGE URL
    # -----------------------------------------------------
    print("\n7. Fetching final data to verify...")
    get_weeds_resp = requests.get(f"{BASE_URL}/pc1/weeds/{mission_id}", headers=headers)
    get_weeds_resp.raise_for_status()
    
    weeds_data = get_weeds_resp.json()
    for w in weeds_data:
        status_str = "✅ Sprayed" if w['is_sprayed'] else "❌ Not Sprayed"
        print(f"  - Weed ID: {w['id']} | Conf: {w['confidence']*100}% | Status: {status_str} at {w['spray_time']}")
        
        # Test frontend image retrieval
        image_req = requests.get(f"{BASE_URL}/pc1/weeds/{mission_id}/{w['id']}/image-url", headers=headers)
        if image_req.status_code == 200:
            print(f"    🔗 Frontend Image URL: {image_req.json()['image_url'][:60]}...")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
