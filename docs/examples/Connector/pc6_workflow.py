import requests
import datetime
import time
import sys
import copy

# Configuration
BASE_URL = "http://147.102.37.125:30080/api/v1"
AUTH_DATA = {"username": "testuser@agribot.local", "password": "testpassword"}

# Assuming field 44 (from your seeds-core.sql) or your designated orchard field ID
FIELD_ID = 44 

def get_iso_now():
    """Helper to get current time in ISO 8601 format with UTC timezone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

# A condensed version of your PC6 Crop Ontology JSON for Thinning
# FOR PRUNING: The structure is identical, but the key "thinning_data" 
# will be named "pruning_data" instead.
SAMPLE_PAYLOAD = {
  "@context": {
    "PO": "http://purl.obolibrary.org/obo/PO_",
    "AGRO": "http://purl.obolibrary.org/obo/AGRO_",
    "PATO": "http://purl.obolibrary.org/obo/PATO_",
    "TO": "http://purl.obolibrary.org/obo/TO_",
    "TreeID": "PO:0000003",
    "Branch": "PO:0009081",
    "Length": "TO:0000641",
    "Diameter": "TO:0000339",
    "Age": "PATO:0000011"
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
      # FOR PRUNING: Rename this key from "thinning_data" to "pruning_data"
      "thinning_data": {
        "BranchesToCutCount": 2,
        "branches": [
          {
            "BranchID": "101-B001",
            "Age_years": 2,
            "Length_m": 0.32,
            "Diameter_cm": 1.8,
            "yolo_detection": {
              "picture_id": "cam_1_tree_101_winter.jpg",
              "class_id": 1,
              "x": 0.6231,
              "y": 0.4795,
              "width": 0.0362,
              "height": 0.2429,
              "confidence": 0.7941
            }
          },
          {
            "BranchID": "101-B089",
            "Age_years": 2,
            "Length_m": 0.47,
            "Diameter_cm": 2.4,
            "yolo_detection": {
              "picture_id": "cam_1_tree_101_winter.jpg",
              "class_id": 1,
              "x": 0.8963,
              "y": 0.8101,
              "width": 0.0136,
              "height": 0.2631,
              "confidence": 0.7843
            }
          }
        ]
      }
    }
  ]
}

def main():
    print("--- AgriBot PC6 Workflow (XR Orchard Thinning & Pruning) ---")

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
        # FOR PRUNING: Change "pc6_thinning" to "pc6_pruning" here
        "mission_type": "pc6_thinning", 
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
    print("\n3. Submitting PC6 Inspection JSON...")
    
    # FOR PRUNING: Change the URL from /thinning/inspection to /pruning/inspection
    inspection_url = f"{BASE_URL}/pc6/missions/{mission_id}/thinning/inspection"
    
    inspection_resp = requests.post(
        inspection_url, 
        json=SAMPLE_PAYLOAD, 
        headers=headers
    )
    
    if inspection_resp.status_code == 200:
        print(f"✓ Inspection data successfully processed & Webhook triggered!")
        print(f"  Response: {inspection_resp.json()['message']}")
    else:
        print(f"❌ Inspection failed: {inspection_resp.text}")

    print("\n   ... Robot traverses the orchard and performs XR cutting ...")
    time.sleep(2)

    # -----------------------------------------------------
    # 4. SUBMIT APPLICATION DATA 
    # -----------------------------------------------------
    print("\n4. Submitting PC6 Application JSON...")
    
    # We modify the payload to represent the application phase
    # (Changing 'BranchesToCutCount' to 'BranchesCutCount')
    application_payload = copy.deepcopy(SAMPLE_PAYLOAD)
    
    for tree in application_payload["trees"]:
        # FOR PRUNING: Change "thinning_data" to "pruning_data" in the lines below
        if "thinning_data" in tree:
            to_cut = tree["thinning_data"].pop("BranchesToCutCount", 0)
            tree["thinning_data"]["BranchesCutCount"] = to_cut
            # Let's simulate a higher confidence after actual cutting
            if len(tree["thinning_data"]["branches"]) > 0:
                tree["thinning_data"]["branches"][0]["yolo_detection"]["confidence"] = 0.99
    
    # FOR PRUNING: Change the URL from /thinning/application to /pruning/application
    application_url = f"{BASE_URL}/pc6/missions/{mission_id}/thinning/application"

    application_resp = requests.post(
        application_url, 
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
    print("\n--- PC6 Workflow Completed Successfully ---")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Network request failed: {e}")