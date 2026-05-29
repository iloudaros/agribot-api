import requests
import datetime
import os
import sys
import api_url 

# Configuration
BASE_URL = api_url.BASE_URL
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}
FIELD_ID = 63 

def get_iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def create_dummy_photo():
    dummy_path = "temp_drone_photo.jpg"
    with open(dummy_path, "wb") as f: 
        f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01dummy_jpg_data_here")
    return dummy_path

def main():
    print("--- AgriBot PC2 Workflow: DTI Drone (Photo Upload & Secure Download) ---")

    photo_to_upload = create_dummy_photo()

    print("\n1. Authenticating...")
    auth_resp = requests.post(f"{BASE_URL}/auth/token", data=AUTH_DATA)
    if auth_resp.status_code != 200:
        print(f"Auth Failed: {auth_resp.text}")
        sys.exit(1)
        
    headers = {"Authorization": f"Bearer {auth_resp.json()['access_token']}", "Content-Type": "application/json"}
    print("✓ Token acquired.")

    print("\n2. Creating Base Mission...")
    mission_resp = requests.post(f"{BASE_URL}/missions", json={
        "field_id": FIELD_ID,
        "mission_type": "pc2_dti", 
        "start_time": get_iso_now()
    }, headers=headers)
    mission_resp.raise_for_status()
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with DB ID: {mission_id}")

    print("\n3. Requesting MinIO upload link for DTI Photo...")
    url_resp = requests.post(f"{BASE_URL}/pc2/dti/photo/presigned-url", json={
        "mission_id": mission_id,
        "filename": "field_survey.jpg"
    }, headers=headers)
    url_resp.raise_for_status()
    
    url_data = url_resp.json()
    photo_upload_url = url_data["upload_url"]
    photo_uri = url_data["photo_uri"]

    print(f"\n4. Uploading '{photo_to_upload}' to MinIO...")
    with open(photo_to_upload, "rb") as f:
        requests.put(photo_upload_url, data=f).raise_for_status()
    print("✓ Photo uploaded successfully.")

    print("\n5. Confirming Photo upload with Database...")
    requests.post(f"{BASE_URL}/pc2/dti/missions/{mission_id}/photo/confirm", json={
        "photo_uri": photo_uri
    }, headers=headers).raise_for_status()
    print(f"✓ PC2 DTI metadata updated. Photo URI saved and timestamp recorded.")

    print("\n6. Closing out Base Mission...")
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()
    print("✓ Base Mission status set to 'complete'.")

    print("\n7. Fetching Latest Photo Metadata...")
    latest_resp = requests.get(f"{BASE_URL}/pc2/dti/fields/{FIELD_ID}/latest-photo", headers=headers)
    
    if latest_resp.status_code == 200:
        latest_data = latest_resp.json()
        secure_photo_url = latest_data['photo_url']
        print(f"  ✓ Latest photo found (Mission ID: {latest_data['mission_id']})")
        print(f"  ✓ Secure Download URL: {secure_photo_url}")
        
        print("\n8. Downloading Photo Securely using JWT Token...")
        # Note: We pass `headers` which contains our Bearer token!
        download_resp = requests.get(secure_photo_url, headers=headers)
        if download_resp.status_code == 200:
            print(f"  ✓ Image securely downloaded! (Size: {len(download_resp.content)} bytes)")
        else:
            print(f"  ❌ Secure download failed: {download_resp.status_code} - {download_resp.text}")

    else:
        print(f"  ❌ Failed to fetch latest photo metadata: {latest_resp.text}")

    if os.path.exists(photo_to_upload):
        os.remove(photo_to_upload)

if __name__ == "__main__":
    try: main()
    except requests.exceptions.RequestException as e: print(f"\n❌ Request failed: {e}")
