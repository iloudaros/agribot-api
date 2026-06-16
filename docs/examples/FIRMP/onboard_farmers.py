import requests
import sys
import api_url 

# Configuration
BASE_URL = api_url.BASE_URL
AUTH_DATA = {
    "username": "admin@agribot.local",
    "password": "testpassword"
}

def main():
    print("--- AgriBot Data Lake Batch Onboarding (Users + Fields + Ownerships) ---")

    # ---------------------------------------------------------
    # 0. Authenticate & Get Token
    # ---------------------------------------------------------
    print("\n1. Authenticating as admin/service provider...")
    auth_resp = requests.post(f"{BASE_URL}/auth/token", data=AUTH_DATA)

    if auth_resp.status_code != 200:
        print(f"Auth Failed: {auth_resp.text}")
        sys.exit(1)

    token = auth_resp.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    print("✓ Token acquired successfully.")

    # ---------------------------------------------------------
    # 1. Batch Upload Users (Upsert Behavior)
    # ---------------------------------------------------------
    print("\n2. Uploading users...")
    users_payload = [
        {
            "id": 1001,
            "email": "mario.rossi@example.com",
            "password": "SecurePassword123!",
            "name": "Mario",
            "role": "farmer",
            "is_active": True
        },
        {
            "id": 1002,
            "email": "anna.smith@example.com",
            "password": "SecurePassword123!",
            "name": "Anna",
            "role": "farmer",
            "is_active": True
        },
        {
            "id": 1003,
            "email": "nikos.papas@example.com",
            "password": "SecurePassword123!",
            "name": "Nikos",
            "role": "farmer",
            "is_active": True
        }
    ]

    users_resp = requests.post(
        f"{BASE_URL}/core/users/batch",
        json=users_payload,
        headers=headers
    )
    users_resp.raise_for_status()
    print(f"✓ Uploaded {len(users_resp.json())} users.")

    # ---------------------------------------------------------
    # 2. Batch Upload Fields (Upsert Behavior)
    # ---------------------------------------------------------
    print("\n3. Uploading fields with explicit IDs (Upsert)...")
    fields_payload = [
        {
            "id": 2001,  # <--- NEW: Explicitly providing an ID
            "name": "North Block - Grapes",
            "crop_name": "Grapes",
            "shape": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [11.9540, 44.4230],
                        [11.9545, 44.4230],
                        [11.9545, 44.4235],
                        [11.9540, 44.4235],
                        [11.9540, 44.4230]
                    ]
                ]
            }
        },
        {
            "id": 2002,  # <--- NEW: Explicitly providing an ID
            "name": "Field 12A - Potatoes",
            "crop_name": "Potato",
            "shape": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [4.8820, 52.3410],
                        [4.8828, 52.3410],
                        [4.8828, 52.3418],
                        [4.8820, 52.3418],
                        [4.8820, 52.3410]
                    ]
                ]
            }
        },
        {
            "id": 2003,  # <--- NEW: Explicitly providing an ID
            "name": "South Olive Sector",
            "crop_name": "Olives",
            "shape": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.3730, 38.2915],
                        [23.3735, 38.2915],
                        [23.3735, 38.2918],
                        [23.3730, 38.2918],
                        [23.3730, 38.2915]
                    ]
                ]
            }
        }
    ]

    fields_resp = requests.post(
        f"{BASE_URL}/core/fields/batch",
        json=fields_payload,
        headers=headers
    )
    fields_resp.raise_for_status()
    print(f"✓ Successfully upserted {len(fields_resp.json())} fields.")

    # ---------------------------------------------------------
    # 3. Batch Assign Field Ownerships
    # ---------------------------------------------------------
    print("\n4. Assigning field ownerships using predetermined IDs...")
    # Because we explicitly defined the IDs above, we don't need complex mapping logic anymore!
    ownerships_payload = {
        "items": [
            {
                "field_id": 2001,
                "user_id": 1001,
                "ownership_percentage": 100.0
            },
            {
                "field_id": 2002,
                "user_id": 1002,
                "ownership_percentage": 100.0
            },
            {
                "field_id": 2003,
                "user_id": 1003,
                "ownership_percentage": 100.0
            }
        ]
    }

    ownerships_resp = requests.post(
        f"{BASE_URL}/core/field-ownerships/batch",
        json=ownerships_payload,
        headers=headers
    )
    ownerships_resp.raise_for_status()
    print(f"✓ {ownerships_resp.json()['message']}")

    # ---------------------------------------------------------
    # 4. Verify Final State
    # ---------------------------------------------------------
    print("\n5. Verifying accessible fields...")
    fields_list_resp = requests.get(f"{BASE_URL}/core/fields", headers=headers)
    fields_list_resp.raise_for_status()
    final_fields = fields_list_resp.json()

    print(f"✓ Retrieved {len(final_fields)} fields from API:")
    for field in final_fields:
        # Only print the ones we just added to keep the output clean
        if field['id'] in [2001, 2002, 2003]:
            print(
                f"  - Field ID: {field['id']} | "
                f"Name: {field['name']} | "
                f"Crop: {field.get('crop_name')} | "
                f"Owners: {field.get('owners', [])}"
            )

    print("\n--- Batch Onboarding Complete! ---")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")