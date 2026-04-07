const fs = require('fs');

// Configuration
const BASE_URL = "http://127.0.0.1:8080/api/v1";
const AUTH_DATA = new URLSearchParams({
  username: "testuser@agribot.local",
  password: "testpassword"
});

// 1. This represents the exact JSON payload that your API forwarded 
// to AgroApps/FIRMP via the background webhook.
// NOTE: Make sure the mission ID in the URL matches a real PC2 mission in your DB!
const DUMMY_FORWARDED_PAYLOAD = {
  parcel_id: 44,
  date: "2026-04-07",
  file_path: "http://127.0.0.1:8080/api/v1/pc2/missions/4/geojson" 
};

async function main() {
  console.log("--- FIRMP Node.js GeoJSON Download Test ---");

  try {
    // -----------------------------------------------------
    // 1. Authenticate (Get JWT Token)
    // -----------------------------------------------------
    console.log("\n1. Authenticating as farmer...");
    const authResponse = await fetch(`${BASE_URL}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: AUTH_DATA
    });

    if (!authResponse.ok) {
      const err = await authResponse.text();
      throw new Error(`Auth Failed: ${err}`);
    }

    const authJson = await authResponse.json();
    const token = authJson.access_token;
    console.log("✓ Token acquired.");

    // -----------------------------------------------------
    // 2. Fetch the Secure GeoJSON File
    // -----------------------------------------------------
    const targetUrl = DUMMY_FORWARDED_PAYLOAD.file_path;
    console.log(`\n2. Securely fetching GeoJSON from:\n   ${targetUrl}`);
    
    const geoJsonResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}` // MUST attach token!
      }
    });

    if (!geoJsonResponse.ok) {
      const err = await geoJsonResponse.text();
      throw new Error(`Download Failed (${geoJsonResponse.status}): ${err}`);
    }

    // -----------------------------------------------------
    // 3. Save it locally
    // -----------------------------------------------------
    const fileData = await geoJsonResponse.text();
    const fileName = `downloaded_parcel_${DUMMY_FORWARDED_PAYLOAD.parcel_id}.geojson`;
    
    fs.writeFileSync(fileName, fileData);
    
    console.log(`\n✓ Success! File downloaded securely.`);
    console.log(`✓ Saved to disk as: ${fileName}`);
    console.log(`✓ File size: ${(fileData.length / 1024).toFixed(2)} KB`);

  } catch (error) {
    console.error(`\n❌ Error: ${error.message}`);
  }
}

main();
