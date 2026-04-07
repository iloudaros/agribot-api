# AgriBot Data Lake API Documentation
**ICCS - NTUA**

## Introduction

This document outlines the architecture and usage of the AgriBot Data Lake API. The platform serves as a central hub for agricultural data ingestion, storage, and retrieval, designed to support various robotic missions ranging from spraying to harvesting.

The system is built on **FastAPI** (API Layer), **PostgreSQL + PostGIS** (Relational & Spatial Data), and **MinIO** (Object Storage for Images/Logs).

---

## Table of Contents 

1. [Architecture Overview](#1-architecture-overview)
2. [Database Schema](#2-database-schema)
3. [Getting Started](#3-getting-started)
   * [Local vs Production Setup](#local-vs-production-setup)
   * [Authentication](#authentication)
4. [Core Resources](#4-core-resources)
   * [Users](#users)
   * [Farms and Fields](#farms-and-fields)
5. [Missions](#5-missions)
6. [Use Cases](#6-use-cases)
   * [🌽🌾 PC1 (AUA): Weed Identification and Spot Spraying for Wheat/Corn](#-pc1-aua-weed-identification-and-spot-spraying-for-wheatcorn)
   * [🥔 PC2 (Ecorobotix): Robotic Spraying of Weeds for Potatoes](#-pc2-ecorobotix-robotic-spraying-of-weeds-for-potatoes)
   * [🥬 PC3 (POLIBA): Robotic Fertilization Management for Leafy Vegetables in Open Field Conditions](#-pc3-poliba-robotic-fertilization-management-for-leafy-vegetables-in-open-field-conditions)
   * [🍅 PC4 (POLIBA): Robotic Technologies for Crop Monitoring and Management in Soilless Tomato Cultivation](#-pc4-poliba-robotic-technologies-for-crop-monitoring-and-management-in-soilless-tomato-cultivation)
   * [🍎🍐 PC5 (KUL): Robotic harvesting in orchards](#-pc5-kul-robotic-harvesting-in-orchards)
   * [🍎🍐 PC6 (KUL): Robotic pruning and thinning with XR in orchards](#-pc6-kul-robotic-pruning-and-thinning-with-xr-in-orchards)
7. [Image & Large File Handling (MinIO)](#7-image--large-file-handling-minio)
   * [The Presigned URL Pattern](#the-presigned-url-pattern)

---

## 1. Architecture Overview

<p align="center">
  <img src="./MCP.svg" alt="MCP Architecture Diagram">
</p>

The platform follows a Data Lake architecture:

*   **API Layer (FastAPI):** Handles authentication, data validation, and orchestration. It does *not* handle heavy file streams directly.
*   **Relational Store (PostgreSQL):** Stores structured data, time-series telemetry, and geospatial boundaries (Fields, Trees).
*   **Object Store (MinIO):** Stores unstructured data like high-resolution images, application maps (GeoJSON), LiDAR point clouds, and raw logs.

---

## 2. Database Schema

<p align="center">
  <img src="./schema.svg" alt="Schema Diagram">
</p>

The database is organized logically into core infrastructure and pilot-case-specific tables.

*   **Core Infrastructure:** `users`, `fields`, `field_ownerships`
*   **Missions (Generic):** `missions`, `mission_types`
*   **Pilot Case 1:** `pc1_weed`, `pc1_missions` (State Machine)
*   **Pilot Case 2:** `pc2_missions` (Links base mission to MinIO GeoJSON URI)
*   **Pilot Case 3:** `pc3_inspections`
*   **Orchards (PC5/6):** `uc5_uc6_trees`, `uc5_uc6_images`, `uc5_uc6_detections`

**Additional Information:**
*   You can view the schema [here](https://dbdiagram.io/d/Agribot-v2-0-69a80db1a3f0aa31e1c704db) 
*   Details about the DB can be found [here](https://dbdocs.io/iloudaros/AgRibot)

---

## 3. Getting Started

### Local vs Production Setup
To start experimenting with the API:
1.  Visit the repository of the [AgriBot Data Lake Local Development Environment](https://github.com/iloudaros/agribot-local)
2.  Follow the instructions to create a local instance of it using [Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Fmacos%2Fx86-64%2Fstable%2Fbinary+download).

*In case you encounter a 404 error with the link above, chances are you are not listed as a contributor at the repository. Please send an email to `iloudaros@microlab.ntua.gr` and we will sort it out.*

For production deployment, please use the infrastructure provided by ICCS.

### Authentication
All API endpoints (except health checks) require a JWT Bearer Token.

**1. Login to get a token:**
```bash
curl -X POST "http://localhost/api/v1/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=testuser@agribot.local&password=testpassword"
```

**2. Use the token:**
Include the header in all requests: `Authorization: Bearer <your_token>`

---

## 4. Core Resources

Before uploading mission data, the infrastructure must be defined.

### Users

#### Connector Side
**Context:** The Connector will have a service account in our database. This account is used to authenticate API calls and push data to the database. The Connector does not manage user accounts for farmers; instead, it relies on the FIRMP platform to handle farmer accounts and push relevant data to our database, so that farmers can later authenticate on the Connector side.

#### FIRMP Side
**Context:** The FIRMP platform is used by farmers. They create their accounts and manage their farms, fields, and missions. So the FIRMP has to be able to push those farmers to our db, so they can later authenticate on the connector side.  At the same time, the FIRMP itself, has its own user in our db so it can get authenticated and push data to our db.

You can see the example of how to onboard farmers in the `docs/examples/FIRMP/onboard_farmers.py` script.

### Fields

#### Connector Side
**Context:** Farmers login using their connector and they are able to download the field boundaries (as GeoJSON) to their local system. The Connector uses this information to geotag the telemetry data and to know where the robot is operating.

#### FIRMP Side
**Context:** The FIRMP platform is used by farmers. They create their accounts and manage their farms, fields, and missions. The Connector will reference these entities when uploading mission data.

---

## 5. Missions
**Context:** A mission represents a specific task performed by a robot, such as spraying, monitoring, or harvesting. Each mission is associated with a specific field, and in essence represents aspecific Pilot Case.

#### Connector Side
All robotic operations share a universal base ⁠Mission. The workflow for any pilot case follows three steps:
  1.  Start Base Mission: `⁠POST /api/v1/missions` (Generates and returns an auto-incrementing integer `⁠id`).
  2.	Upload Specific Data: Use the specific PC endpoints (e.g., `⁠/pc1/weeds/batch` or `/pc2/geojson/confirm`) and link them using the `⁠mission_id` integer.	
  3.	End Base Mission: `⁠PATCH /api/v1/missions/{mission_id}` to set the `⁠end_time` and `⁠status` to `⁠complete`.

#### FIRMP Side
**Context:** The FIRMP platform is used by farmers. They are able to see the results of the missions in the FIRMP dashboard, so they can make informed decisions about their farming operations. Our API pushes the data to the FIRMP platform for visualization and analysis via Webhooks.

---

## 6. Use Cases

### 🌽🌾 PC1 (AUA): Weed Identification and Spot Spraying for Wheat/Corn" 
**Context:** A UGV traverses a field, inspects it for weeds, and later performs a spraying pass. State changes trigger background webhooks to AgroApps.

> **Full Example:** See ⁠`docs/examples/Connector/pc1_workflow.py`.

#### Connector Side
1. **Create the Base Mission** 
`POST /api/v1/missions`
2. **Update PC1 State to Ongoing** 
`PUT /api/v1/pc1/missions/1/state`
3. **Batch Upload Inspected Weeds** 
Upload weeds detected by the UGV (includes uploading images to MinIO via presigned URLs). 
`POST /api/v1/pc1/weeds/batch`
4. **Mark Inspection Complete** 
Triggers a webhook to AgroApps. 
`PUT /api/v1/pc1/missions/1/state`
5. **Batch Update Weeds as Sprayed** 
`PATCH /api/v1/pc1/weeds/batch`
6. **Mark Spraying Complete & Close Mission** 
Triggers the final webhook. 
`PUT /api/v1/pc1/missions/1/state` and `PATCH /api/v1/missions/1`

#### FIRMP Side
We push the data to the FIRMP platform for visualization and analysis via Webhooks containing 7-day public MinIO image links.

---

### 🥔 PC2 (Ecorobotix): Robotic Spraying of Weeds for Potatoes
**Context:** Robots traversing a field to spray liquids on weeds. Generates a large Application Map (GeoJSON) detailing sprayed zones.



#### Connector Side

> **Full Example:** See `docs/examples/Connector/pc2_workflow.py`

Because the Application Map is a large GeoJSON file, it is stored in MinIO rather than PostgreSQL to ensure database performance.
1. **Create the Base Mission** 
`POST /api/v1/missions` -> Returns `mission_id`.
2. **Request Upload URL** 
`POST /api/v1/pc2/geojson/presigned-url` -> Returns a temporary MinIO `PUT` link and a `geojson_uri`.
3. **Upload File** 
The connector securely uploads the file directly to MinIO using the generated URL.
4. **Confirm Upload** 
`POST /api/v1/pc2/missions/{mission_id}/geojson/confirm`.
   * *Note: Confirming the upload automatically triggers a background webhook to AgroApps (`/spraying` endpoint).*
5. **Close Mission** 
`PATCH /api/v1/missions/{mission_id}` -> Set status to `complete`.

#### FIRMP Side

> **Full Example:** See `docs/examples/FIRMP/pc2_workflow.js`.

When the upload is confirmed, the API forwards a JSON payload to AgroApps. To maintain security, the `file_path` provided in the payload is **not** a public MinIO link. It is a secure FastAPI endpoint.

```json
{
  "parcel_id": 44,
  "date": "2026-04-07",
  "file_path": "http://127.0.0.1:8080/api/v1/pc2/missions/2/geojson"
}
```

To download the file, the FIRMP frontend or backend must perform an HTTP `GET` request to that `file_path`, passing the farmer's JWT token in the headers:
`Authorization: Bearer <TOKEN>`

The FastAPI server will verify permissions and securely stream the GeoJSON from MinIO back to the client.

---

### 🥬 PC3 (POLIBA): Robotic Fertilization Management for Leafy Vegetables in Open Field Conditions
**Context:** Robots scanning crops (Leafy vegetables, Tomatoes) to measure growth indices like NDVI or Biomass.

> **Full Example:** See ⁠`docs/examples/Connector/pc3_workflow.py`.

#### Connector Side
1. **Create the Base Mission** 
`POST /api/v1/missions`
2. **Upload Batch Telemetry** 
Send arrays of spatial data including NDVI, Biomass, and bounding box dimensions. `POST /api/v1/pc3/inspections/batch`
3. **Close Mission** 
`PATCH /api/v1/missions/{mission_id}` -> Setting to `complete` triggers the AgroApps Webhook containing all telemetry points.

#### FIRMP Side
We push the data to the FIRMP platform for visualization and analysis upon mission completion.

---

### 🍅 PC4 (POLIBA): Robotic Technologies for Crop Monitoring and Management in Soilless Tomato Cultivation
**Context:** Robots scanning crops (Leafy vegetables, Tomatoes) to measure growth indices like NDVI or Biomass.

#### Connector Side
... *(Pending Implementation)*

#### FIRMP Side
... *(Pending Implementation)*

---

### 🍎🍐 PC5 (KUL): Robotic harvesting in orchards
**Context:** Managing individual trees, harvesting fruit, and running AI detections on images.

... *(Pending Implementation)*

---

### 🍎🍐 PC6 (KUL): Robotic pruning and thinning with XR in orchards
**Context:** Managing individual trees, harvesting fruit, and running AI detections on images.

... *(Pending Implementation)*

---

## 7. Image & Large File Handling (MinIO)

We use MinIO for storing large files (Images, GeoJSON maps). To ensure high performance and prevent the FastAPI server from becoming a bottleneck, we use **Presigned URLs**. 

### The Presigned URL Pattern

1.  **Request URL:** The Connector calls an endpoint like `POST /api/v1/pc2/geojson/presigned-url`. The API asks MinIO to generate a cryptographic, temporary URL.
2.  **Direct Upload:** The API returns the URL. The Connector performs a `PUT` request to this URL, sending the binary data **directly to the storage server** (bypassing FastAPI entirely).
3.  **Confirm (Optional but recommended):** The Connector calls a confirmation endpoint (e.g., `POST /api/v1/pc2/missions/{id}/geojson/confirm`) to tell the API the upload is finished. The API then saves the reference URI (`minio://...`) to PostgreSQL and triggers any necessary webhooks.
4.  **Secure Download:** For sensitive files (like PC2 GeoJSON maps), the API provides an endpoint that streams the file from MinIO back to the client, but only after validating the user's JWT token and field access rights.

