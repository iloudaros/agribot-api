import requests
import datetime
import os
import sys

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

# From seeds-core.sql, Field 44 is "Field 26 - Demo Spraying" (Potato) owned by testuser
FIELD_ID = 44 

# Paths to the sample files
GEOJSON_FILE_PATH = "../../../data_samples/UC2/Ecorobotix/mission.geojson"
GEOTIFF_FILE_PATH = "../../../data_samples/UC2/Ecorobotix/application_map.tif"

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def create_dummy_geojson():
    """Creates a temporary dummy geojson if the real one isn't found."""
    dummy_path = "temp_mission.geojson"
    with open(dummy_path, "w") as f:
        f.write('{"type": "FeatureCollection", "features": []}')
    return dummy_path

def create_dummy_geotiff():
    """Creates a temporary dummy geotiff (with standard TIFF header) if the real one isn't found."""
    dummy_path = "temp_map.tif"
    with open(dummy_path, "wb") as f:
        # standard little-endian tiff magic number just to have some bytes
        f.write(b"II*\x00\x08\x00\x00\x00dummy_geotiff_data_here")
    return dummy_path

def main():
    print("--- AgriBot PC2 Workflow (GeoJSON & GeoTIFF Upload) ---")

    # Ensure we have files to upload
    geojson_to_upload = GEOJSON_FILE_PATH
    if not os.path.exists(geojson_to_upload):
        print(f"⚠️ Sample file not found at {GEOJSON_FILE_PATH}. Creating a temporary dummy file.")
        geojson_to_upload = create_dummy_geojson()

    geotiff_to_upload = GEOTIFF_FILE_PATH
    if not os.path.exists(geotiff_to_upload):
        print(f"⚠️ Sample file not found at {GEOTIFF_FILE_PATH}. Creating a temporary dummy file.")
        geotiff_to_upload = create_dummy_geotiff()


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


    # =====================================================
    # GEOJSON WORKFLOW
    # =====================================================
    print("\n3. Requesting secure MinIO upload link for GeoJSON...")
    url_resp = requests.post(f"{BASE_URL}/pc2/geojson/presigned-url", json={
        "mission_id": mission_id,
        "filename": os.path.basename(geojson_to_upload)
    }, headers=headers)
    url_resp.raise_for_status()
    
    url_data = url_resp.json()
    geojson_upload_url = url_data["upload_url"]
    geojson_uri = url_data["geojson_uri"]

    print(f"\n4. Uploading '{geojson_to_upload}' to MinIO...")
    with open(geojson_to_upload, "rb") as f:
        upload_resp = requests.put(geojson_upload_url, data=f)
        upload_resp.raise_for_status()
    print("✓ GeoJSON uploaded successfully.")

    print("\n5. Confirming GeoJSON upload with Database...")
    confirm_resp = requests.post(f"{BASE_URL}/pc2/missions/{mission_id}/geojson/confirm", json={
        "geojson_uri": geojson_uri
    }, headers=headers)
    confirm_resp.raise_for_status()
    print(f"✓ PC2 Mission metadata updated with GeoJSON URI: {geojson_uri}")


    # =====================================================
    # GEOTIFF WORKFLOW
    # =====================================================
    print("\n6. Requesting secure MinIO upload link for GeoTIFF...")
    tiff_url_resp = requests.post(f"{BASE_URL}/pc2/geotiff/presigned-url", json={
        "mission_id": mission_id,
        "filename": os.path.basename(geotiff_to_upload)
    }, headers=headers)
    tiff_url_resp.raise_for_status()
    
    tiff_url_data = tiff_url_resp.json()
    geotiff_upload_url = tiff_url_data["upload_url"]
    geotiff_uri = tiff_url_data["geotiff_uri"]

    print(f"\n7. Uploading '{geotiff_to_upload}' to MinIO...")
    with open(geotiff_to_upload, "rb") as f:
        upload_resp = requests.put(geotiff_upload_url, data=f)
        upload_resp.raise_for_status()
    print("✓ GeoTIFF uploaded successfully.")

    print("\n8. Confirming GeoTIFF upload with Database...")
    tiff_confirm_resp = requests.post(f"{BASE_URL}/pc2/missions/{mission_id}/geotiff/confirm", json={
        "geotiff_uri": geotiff_uri
    }, headers=headers)
    tiff_confirm_resp.raise_for_status()
    print(f"✓ PC2 Mission metadata updated with GeoTIFF URI: {geotiff_uri}")


    # -----------------------------------------------------
    # 9. CLOSE OUT BASE MISSION
    # -----------------------------------------------------
    print("\n9. Closing out Base Mission...")
    close_resp = requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers)
    close_resp.raise_for_status()
    print("✓ Base Mission status set to 'complete'.")


    # -----------------------------------------------------
    # 10. TEST SECURE DOWNLOADS
    # -----------------------------------------------------
    print("\n10. Testing Secure Downloads...")
    
    # Test GeoJSON
    download_geojson = requests.get(f"{BASE_URL}/pc2/missions/{mission_id}/geojson", headers=headers)
    if download_geojson.status_code == 200:
        print(f"  ✓ GeoJSON downloaded securely! (Size: {len(download_geojson.content)} bytes)")
    else:
        print(f"  ❌ Failed to download GeoJSON: {download_geojson.text}")

    # Test GeoTIFF
    download_geotiff = requests.get(f"{BASE_URL}/pc2/missions/{mission_id}/geotiff", headers=headers)
    if download_geotiff.status_code == 200:
        print(f"  ✓ GeoTIFF downloaded securely! (Size: {len(download_geotiff.content)} bytes)")
    else:
        print(f"  ❌ Failed to download GeoTIFF: {download_geotiff.text}")


    # Cleanup dummy files if we created them
    if geojson_to_upload == "temp_mission.geojson":
        os.remove(geojson_to_upload)
    if geotiff_to_upload == "temp_map.tif":
        os.remove(geotiff_to_upload)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
