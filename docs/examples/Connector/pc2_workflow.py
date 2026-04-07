import requests
import datetime
import os
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

# From seeds-core.sql, Field 44 is "Field 26 - Demo Spraying" (Potato) owned by testuser
FIELD_ID = 44 

# Path to the sample geojson file in your repository
GEOJSON_FILE_PATH = "../../../data_samples/UC2/Ecorobotix/mission.geojson"

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def create_dummy_geojson():
    """Creates a temporary dummy geojson if the real one isn't found."""
    dummy_path = "temp_mission.geojson"
    with open(dummy_path, "w") as f:
        f.write('{"type": "FeatureCollection", "features": []}')
    return dummy_path

def main():
    print("--- AgriBot PC2 Workflow (GeoJSON Upload) ---")

    # Ensure we have a file to upload
    file_to_upload = GEOJSON_FILE_PATH
    if not os.path.exists(file_to_upload):
        print(f"⚠️ Sample file not found at {GEOJSON_FILE_PATH}. Creating a temporary dummy file.")
        file_to_upload = create_dummy_geojson()

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
        "mission_type": "pc2_spraying",
        "start_time": get_iso_now()
    }, headers=headers)
    mission_resp.raise_for_status()
    
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with DB ID: {mission_id}")

    # -----------------------------------------------------
    # 3. REQUEST MINIO PRESIGNED URL
    # -----------------------------------------------------
    print("\n3. Requesting secure MinIO upload link...")
    url_resp = requests.post(f"{BASE_URL}/pc2/geojson/presigned-url", json={
        "mission_id": mission_id,
        "filename": os.path.basename(file_to_upload)
    }, headers=headers)
    url_resp.raise_for_status()
    
    url_data = url_resp.json()
    upload_url = url_data["upload_url"]
    geojson_uri = url_data["geojson_uri"]
    print(f"✓ Received upload URL for MinIO bucket: {url_data['bucket']}")

    # -----------------------------------------------------
    # 4. UPLOAD FILE DIRECTLY TO MINIO
    # -----------------------------------------------------
    print(f"\n4. Uploading '{file_to_upload}' to MinIO (bypassing FastAPI)...")
    
    # Notice we don't use the 'headers' with the JWT token here. 
    # MinIO uses the cryptographic signature inside the upload_url itself.
    file_size = os.path.getsize(file_to_upload)
    with open(file_to_upload, "rb") as f:
        # We must use PUT, as the presigned URL was generated for a PUT request
        upload_resp = requests.put(upload_url, data=f)
        upload_resp.raise_for_status()
        
    print(f"✓ File uploaded successfully ({file_size / 1024:.1f} KB).")

    # -----------------------------------------------------
    # 5. CONFIRM UPLOAD WITH DATABASE
    # -----------------------------------------------------
    print("\n5. Confirming upload & saving metadata to PostgreSQL...")
    confirm_resp = requests.post(f"{BASE_URL}/pc2/missions/{mission_id}/geojson/confirm", json={
        "geojson_uri": geojson_uri
    }, headers=headers)
    confirm_resp.raise_for_status()
    print(f"✓ PC2 Mission metadata saved! MinIO URI: {confirm_resp.json()['geojson_uri']}")

    # -----------------------------------------------------
    # 6. CLOSE OUT BASE MISSION
    # -----------------------------------------------------
    print("\n6. Closing out Base Mission...")
    close_resp = requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers)
    close_resp.raise_for_status()
    print("✓ Base Mission status set to 'complete'.")

        # -----------------------------------------------------
    # 7. TEST SECURE DOWNLOAD
    # -----------------------------------------------------
    print("\n7. Testing Secure GeoJSON Download...")
    download_resp = requests.get(f"{BASE_URL}/pc2/missions/{mission_id}/geojson", headers=headers)
    
    if download_resp.status_code == 200:
        file_bytes = download_resp.content
        print(f"✓ GeoJSON downloaded securely via API! (Size: {len(file_bytes)} bytes)")
        
        # Optional: Save it to verify contents
        # with open("test_download.geojson", "wb") as f:
        #     f.write(file_bytes)
    else:
        print(f"❌ Failed to download GeoJSON: {download_resp.text}")


    # Cleanup dummy file if we created it
    if file_to_upload == "temp_mission.geojson":
        os.remove(file_to_upload)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
