import requests
import datetime
import os
import sys
import api_url

# Configuration
BASE_URL = api_url.BASE_URL
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}
FIELD_ID = 44

GEOJSON_FILE_PATH = "../../../data_samples/UC2/Ecorobotix/mission.geojson"

def get_iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def create_dummy_geojson():
    dummy_path = "temp_mission.geojson"
    with open(dummy_path, "w") as f: f.write('{"type": "FeatureCollection", "features": []}')
    return dummy_path

def main():
    print("--- AgriBot PC2 Workflow: Ecorobotix (GeoJSON Only) ---")

    geojson_to_upload = GEOJSON_FILE_PATH if os.path.exists(GEOJSON_FILE_PATH) else create_dummy_geojson()

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
        "mission_type": "pc2_ecorobotix",
        "start_time": get_iso_now()
    }, headers=headers)
    mission_resp.raise_for_status()
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with DB ID: {mission_id}")

    # =====================================================
    # GEOJSON WORKFLOW
    # =====================================================
    print("\n3. Requesting secure MinIO upload link for GeoJSON...")
    url_resp = requests.post(f"{BASE_URL}/pc2/ecorobotix/geojson/presigned-url", json={
        "mission_id": mission_id,
        "filename": os.path.basename(geojson_to_upload)
    }, headers=headers)
    url_resp.raise_for_status()
    geojson_uri = url_resp.json()["geojson_uri"]

    print(f"\n4. Uploading '{geojson_to_upload}' to MinIO...")
    with open(geojson_to_upload, "rb") as f:
        requests.put(url_resp.json()["upload_url"], data=f).raise_for_status()
    print("✓ GeoJSON uploaded successfully.")

    print("\n5. Confirming GeoJSON upload with Database...")
    requests.post(f"{BASE_URL}/pc2/ecorobotix/missions/{mission_id}/geojson/confirm", json={
        "geojson_uri": geojson_uri
    }, headers=headers).raise_for_status()
    print(f"✓ Metadata updated with GeoJSON URI: {geojson_uri}")

    print("\n6. Closing out Base Mission...")
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()
    print("✓ Mission closed.")

    print("\n7. Testing Secure Downloads...")
    download_geojson = requests.get(f"{BASE_URL}/pc2/ecorobotix/missions/{mission_id}/geojson", headers=headers)
    print(f"  ✓ GeoJSON downloaded: {len(download_geojson.content)} bytes" if download_geojson.status_code == 200 else f"  ❌ Failed GeoJSON: {download_geojson.text}")

    if geojson_to_upload == "temp_mission.geojson": os.remove(geojson_to_upload)

if __name__ == "__main__":
    try: main()
    except requests.exceptions.RequestException as e: print(f"\n❌ Request failed: {e}")