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
  geojson_path: "http://127.0.0.1:8080/api/v1/pc2/missions/4/geojson",
  geotiff_path: "http://127.0.0.1:8080/api/v1/pc2/missions/4/geotiff"
};

async function main() {
  console.log("--- FIRMP Node.js PC2 Download Test (GeoJSON & GeoTIFF) ---");

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
    // 2. Fetch & Save the Secure GeoJSON File
    // -----------------------------------------------------
    const geojsonUrl = DUMMY_FORWARDED_PAYLOAD.geojson_path;
    console.log(`\n2. Securely fetching GeoJSON from:\n   ${geojsonUrl}`);
    
    const geoJsonResponse = await fetch(geojsonUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}` // MUST attach token!
      }
    });

    if (!geoJsonResponse.ok) {
      const err = await geoJsonResponse.text();
      throw new Error(`GeoJSON Download Failed (${geoJsonResponse.status}): ${err}`);
    }

    const geoJsonData = await geoJsonResponse.text();
    const geoJsonFileName = `downloaded_parcel_${DUMMY_FORWARDED_PAYLOAD.parcel_id}.geojson`;
    fs.writeFileSync(geoJsonFileName, geoJsonData);
    
    console.log(`✓ Success! GeoJSON downloaded securely.`);
    console.log(`✓ Saved to disk as: ${geoJsonFileName}`);
    console.log(`✓ File size: ${(geoJsonData.length / 1024).toFixed(2)} KB`);


    // -----------------------------------------------------
    // 3. Fetch & Save the Secure GeoTIFF File (Binary)
    // -----------------------------------------------------
    const geotiffUrl = DUMMY_FORWARDED_PAYLOAD.geotiff_path;
    console.log(`\n3. Securely fetching GeoTIFF from:\n   ${geotiffUrl}`);
    
    const geoTiffResponse = await fetch(geotiffUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}` // MUST attach token!
      }
    });

    if (!geoTiffResponse.ok) {
      const err = await geoTiffResponse.text();
      throw new Error(`GeoTIFF Download Failed (${geoTiffResponse.status}): ${err}`);
    }

    // Convert the response to an ArrayBuffer, then a Node.js Buffer for binary writing
    const arrayBuffer = await geoTiffResponse.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const geoTiffFileName = `downloaded_parcel_${DUMMY_FORWARDED_PAYLOAD.parcel_id}_map.tif`;
    
    fs.writeFileSync(geoTiffFileName, buffer);
    
    console.log(`✓ Success! GeoTIFF downloaded securely.`);
    console.log(`✓ Saved to disk as: ${geoTiffFileName}`);
    console.log(`✓ File size: ${(buffer.length / 1024).toFixed(2)} KB`);

  } catch (error) {
    console.error(`\n❌ Error: ${error.message}`);
  }
}

main();
