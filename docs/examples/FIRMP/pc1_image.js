import React, { useState, useEffect } from 'react';

const WeedImage = ({ inspectionId, weedId, token }) => {
  const [imageUrl, setImageUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchPresignedUrl = async () => {
      try {
        // 1. Ask the API for a temporary MinIO access link
        const response = await fetch(
          `http://localhost:8080/api/v1/pc1/weeds/${inspectionId}/${weedId}/image-url`,
          {
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          }
        );

        if (!response.ok) {
          throw new Error('Failed to fetch image URL');
        }

        const data = await response.json();
        
        // 2. Save the URL to state so the <img> tag can use it
        setImageUrl(data.image_url);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchPresignedUrl();
  }, [inspectionId, weedId, token]);

  if (loading) return <div>Loading image...</div>;
  if (error) return <div>Error loading image: {error}</div>;

  // 3. Render the image directly from MinIO using the presigned URL
  return (
    <div className="weed-card">
      <h4>Weed #{weedId}</h4>
      {imageUrl ? (
        <img 
          src={imageUrl} 
          alt={`Weed ${weedId} from inspection ${inspectionId}`} 
          style={{ maxWidth: '300px', borderRadius: '8px' }}
        />
      ) : (
        <p>No image available</p>
      )}
    </div>
  );
};

export default WeedImage;
