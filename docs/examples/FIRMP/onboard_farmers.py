import requests
import sys

BASE_URL = "http://127.0.0.1:8080/api/v1"
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
    # 1. Batch Upload Users
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
    created_users = users_resp.json()

    user_id_map = {user["email"]: user["id"] for user in created_users}
    print(f"✓ Uploaded {len(created_users)} users: {user_id_map}")

    # ---------------------------------------------------------
    # 2. Batch Upload Fields
    # ---------------------------------------------------------
    print("\n3. Uploading fields...")
    fields_payload = [
        {
            "name": "North Block - Grapes",
            "crop_name": "Grapes",
            "center_lat": 44.42325,
            "center_lon": 11.95425,
            "boundary_wkt": "POLYGON((11.9540 44.4230, 11.9545 44.4230, 11.9545 44.4235, 11.9540 44.4235, 11.9540 44.4230))"
        },
        {
            "name": "Field 12A - Potatoes",
            "crop_name": "Potato",
            "center_lat": 52.3414,
            "center_lon": 4.8824,
            "boundary_wkt": "POLYGON((4.8820 52.3410, 4.8828 52.3410, 4.8828 52.3418, 4.8820 52.3418, 4.8820 52.3410))"
        },
        {
            "name": "South Olive Sector",
            "crop_name": "Olives",
            "center_lat": 38.29165,
            "center_lon": 23.37325,
            "boundary_wkt": "POLYGON((23.3730 38.2915, 23.3735 38.2915, 23.3735 38.2918, 23.3730 38.2918, 23.3730 38.2915))"
        }
    ]

    fields_resp = requests.post(
        f"{BASE_URL}/core/fields/batch",
        json=fields_payload,
        headers=headers
    )
    fields_resp.raise_for_status()
    created_fields = fields_resp.json()

    field_id_map = {field["name"]: field["id"] for field in created_fields}
    print(f"✓ Uploaded {len(created_fields)} fields: {field_id_map}")

    # ---------------------------------------------------------
    # 3. Batch Assign Field Ownerships
    # ---------------------------------------------------------
    print("\n4. Assigning field ownerships...")
    ownerships_payload = {
        "items": [
            {
                "field_id": field_id_map["North Block - Grapes"],
                "user_id": user_id_map["mario.rossi@example.com"],
                "ownership_percentage": 100.0
            },
            {
                "field_id": field_id_map["Field 12A - Potatoes"],
                "user_id": user_id_map["anna.smith@example.com"],
                "ownership_percentage": 100.0
            },
            {
                "field_id": field_id_map["South Olive Sector"],
                "user_id": user_id_map["nikos.papas@example.com"],
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
