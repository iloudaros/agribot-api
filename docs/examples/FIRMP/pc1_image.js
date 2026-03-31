async function fetchWeedImage(inspectionId, weedId, token) {
  const response = await fetch(`http://localhost:8080/api/v1/pc1/weeds/${inspectionId}/${weedId}/image-url`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  if (response.ok) {
    const data = await response.json();
    return data.image_url; // Returns the temporary MinIO URL
  }
  return null;
}

// Inside your React component:
// <img src={fetchedUrl} alt="Detected Weed" />
