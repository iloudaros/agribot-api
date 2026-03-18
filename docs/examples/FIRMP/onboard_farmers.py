# This script demonstrates how to batch onboard farmers, their farms, and fields into the AgriBot Data Lake using the API.
#  It performs the following steps:
# 1. Authenticates as a service provider to get an access token.
# 2. Batch uploads multiple users (farmers) to the database.
# 3. Batch uploads farms associated with the newly created users.
# 4. Batch uploads fields associated with the newly created farms.
# It is intended to be used by the FIRMP platform to onboard farmers and their data.
import requests
import sys

# Configuration
BASE_URL = "http://127.0.0.1:8080/api/v1"
AUTH_DATA = {
    "username": "admin",  # Replace with actual username from your dev env
    "password": "testpassword"  # Replace with actual password from your dev env
}

def main():
    print("--- AgriBot Data Lake Batch Onboarding ---")

    # ---------------------------------------------------------
    # 0. Authenticate & Get Token
    # ---------------------------------------------------------
    print("\n1. Authenticating as service provider...")
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
    print("\n2. Uploading Users...")
    users_payload = [
        {"username": "mario.rossi", "password": "SecurePassword123!", "name": "Mario", "surname": "Rossi", "role": "farmer", "is_active": True},
        {"username": "anna.smith", "password": "SecurePassword123!", "name": "Anna", "surname": "Smith", "role": "farmer", "is_active": True},
        {"username": "nikos.papas", "password": "SecurePassword123!", "name": "Nikos", "surname": "Papas", "role": "farmer", "is_active": True}
    ]

    users_resp = requests.post(f"{BASE_URL}/core/users/batch", json=users_payload, headers=headers)
    users_resp.raise_for_status()
    created_users = users_resp.json()
    
    # Create a mapping of username -> new Database ID
    user_id_map = {user["username"]: user["id"] for user in created_users}
    print(f"✓ Uploaded {len(created_users)} users: {user_id_map}")

    # ---------------------------------------------------------
    # 2. Batch Upload Farms (Using the new User IDs)
    # ---------------------------------------------------------
    print("\n3. Uploading Farms...")
    farms_payload = [
        {
            "name": "Rossi Vineyards",
            "center_lat": 44.4231,
            "center_lon": 11.9542,
            "owner_id": user_id_map["mario.rossi"]
        },
        {
            "name": "Smith Organic Potatoes",
            "center_lat": 52.3412,
            "center_lon": 4.8821,
            "owner_id": user_id_map["anna.smith"]
        },
        {
            "name": "Papas Olive Grove",
            "center_lat": 38.2915,
            "center_lon": 23.3730,
            "owner_id": user_id_map["nikos.papas"]
        }
    ]

    farms_resp = requests.post(f"{BASE_URL}/core/farms/batch", json=farms_payload, headers=headers)
    farms_resp.raise_for_status()
    created_farms = farms_resp.json()
    
    # Create a mapping of farm name -> new Database ID
    farm_id_map = {farm["name"]: farm["id"] for farm in created_farms}
    print(f"✓ Uploaded {len(created_farms)} farms: {farm_id_map}")

    # ---------------------------------------------------------
    # 3. Batch Upload Fields (Using the new Farm IDs)
    # ---------------------------------------------------------
    print("\n4. Uploading Fields...")
    fields_payload = [
        {
            "farm_id": farm_id_map["Rossi Vineyards"],
            "name": "North Block - Grapes",
            "crop_name": "Grapes",
            "boundary_wkt": "POLYGON((11.9540 44.4230, 11.9545 44.4230, 11.9545 44.4235, 11.9540 44.4235, 11.9540 44.4230))"
        },
        {
            "farm_id": farm_id_map["Smith Organic Potatoes"],
            "name": "Field 12A - Potatoes",
            "crop_name": "Potato",
            "boundary_wkt": "POLYGON((4.8820 52.3410, 4.8828 52.3410, 4.8828 52.3418, 4.8820 52.3418, 4.8820 52.3410))"
        },
        {
            "farm_id": farm_id_map["Papas Olive Grove"],
            "name": "South Olive Sector",
            "crop_name": "Olives",
            "boundary_wkt": "POLYGON((23.3730 38.2915, 23.3735 38.2915, 23.3735 38.2918, 23.3730 38.2918, 23.3730 38.2915))"
        }
    ]

    fields_resp = requests.post(f"{BASE_URL}/core/fields/batch", json=fields_payload, headers=headers)
    fields_resp.raise_for_status()
    created_fields = fields_resp.json()
    
    print(f"✓ Uploaded {len(created_fields)} fields.")
    print("\n--- Batch Onboarding Complete! ---")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        if e.response is not None:
            print(f"Server replied: {e.response.text}")
