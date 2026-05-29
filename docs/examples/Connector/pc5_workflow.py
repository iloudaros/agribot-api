import requests
import datetime
import time
import sys
import copy
import api_url 

# Configuration
BASE_URL = api_url.BASE_URL
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

FIELD_ID = 48

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

# A condensed version of our JSON
SAMPLE_PAYLOAD = {
  "@context": {
    "PO": "http://purl.obolibrary.org/obo/PO_",
    "AGRO": "http://purl.obolibrary.org/obo/AGRO_",
    "PATO": "http://purl.obolibrary.org/obo/PATO_",
    "CO_370": "https://cropontology.org/rdf/CO_370:",
    "TreeID": "PO:0000003",
    "Variety": "AGRO:00000616",
    "Rootstock": "PO:0004542",
    "PlantingDate": "AGRO:00010133",
    "FruitCount": "CO_370:0001023"
  },
  "trees": [
    {
      "tree_metadata": {
        "TreeID": "MALUS-GALA-101",
        "Variety": "Gala",
        "Rootstock": "M9",
        "PlantingDate": 2021
      },
      "location": {
        "grid": {
          "AGRO:00000155": 1,
          "PATO:0000140": 1
        },
        "geolocation": {
          "AGRO:00000574": 46.498121,
          "AGRO:00000575": 11.348922,
          "AGRO:00000612": 254.5
        }
      },
      "harvest_data": {
        "FruitCount": 2,
        "apples": [
          {
            "AppleID": "101-001",
            "SizeClass": "CO_370:0000909",
            "OvercolorClass": "CO_370:0000884",
            "yolo_detection": {
              "picture_id": "cam_1_tree_101.jpg",
              "class_id": 0,
              "x": 0.2263,
              "y": 0.67,
              "width": 0.0626,
              "height": 0.0232,
              "confidence": 0.954
            }
          },
          {
            "AppleID": "101-002",
            "SizeClass": "CO_370:0000909",
            "OvercolorClass": "CO_370:0000872",
            "yolo_detection": {
              "picture_id": "cam_1_tree_101.jpg",
              "class_id": 0,
              "x": 0.9057,
              "y": 0.4687,
              "width": 0.0648,
              "height": 0.0526,
              "confidence": 0.7981
            }
          }
        ]
      }
    }
  ]
}

def main():
    print("--- AgriBot PC5 Workflow (Orchard Harvesting & Inspection) ---")

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
        "mission_type": "pc5_harvest",
        "start_time": get_iso_now()
    }, headers=headers)
    
    if mission_resp.status_code != 201:
        print(f"Failed to create mission: {mission_resp.text}")
        sys.exit(1)
        
    mission_id = mission_resp.json()["id"]
    print(f"✓ Base Mission created with DB ID: {mission_id}")

    # -----------------------------------------------------
    # 3. SUBMIT INSPECTION DATA
    # -----------------------------------------------------
    print("\n3. Submitting PC5 Inspection JSON...")
    
    inspection_resp = requests.post(
        f"{BASE_URL}/pc5/missions/{mission_id}/inspection", 
        json=SAMPLE_PAYLOAD, 
        headers=headers
    )
    
    if inspection_resp.status_code == 200:
        print(f"✓ Inspection data successfully processed & Webhook triggered!")
        print(f"  Response: {inspection_resp.json()['message']}")
    else:
        print(f"❌ Inspection failed: {inspection_resp.text}")

    print("\n   ... Robot traverses the orchard ...")
    time.sleep(2)

    # -----------------------------------------------------
    # 4. SUBMIT APPLICATION (HARVESTING) DATA
    # -----------------------------------------------------
    print("\n4. Submitting PC5 Application JSON...")
    
    # We'll just modify the payload slightly to simulate the application phase
    application_payload = copy.deepcopy(SAMPLE_PAYLOAD)
    application_payload["trees"][0]["harvest_data"]["apples"][0]["confidence"] = 0.999
    
    application_resp = requests.post(
        f"{BASE_URL}/pc5/missions/{mission_id}/application", 
        json=application_payload, 
        headers=headers
    )
    
    if application_resp.status_code == 200:
        print(f"✓ Application data successfully processed & Webhook triggered!")
        print(f"  Response: {application_resp.json()['message']}")
    else:
        print(f"❌ Application failed: {application_resp.text}")

    # -----------------------------------------------------
    # 5. CLOSE OUT BASE MISSION
    # -----------------------------------------------------
    print("\n5. Closing out Base Mission...")
    requests.patch(f"{BASE_URL}/missions/{mission_id}", json={
        "status": "complete",
        "end_time": get_iso_now()
    }, headers=headers).raise_for_status()
    print("✓ Base Mission status set to complete.")
    print("\n--- PC5 Workflow Completed Successfully ---")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Network request failed: {e}")