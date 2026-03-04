from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import uuid

# --- 1. Core Infrastructure ---

class RobotCreate(BaseModel):
    name: str
    serial_number: str
    type: str
    firmware_version: Optional[str] = None

class Robot(RobotCreate):
    id: int

class FarmCreate(BaseModel):
    name: str
    owner_name: Optional[str] = None
    center_lat: float
    center_lon: float

class FieldCreate(BaseModel):
    farm_id: int
    name: str
    crop_name: Optional[str] = None
    # Accepting a simple WKT string for polygon for simplicity
    boundary_wkt: Optional[str] = None 

# --- 2. UC1 & UC2: Spraying ---

class SprayingMissionCreate(BaseModel):
    robot_id: int
    field_id: int
    mission_type: str = "spraying"
    start_time: datetime
    end_time: Optional[datetime] = None
    travelled_distance_m: Optional[float] = 0.0
    covered_area_m2: Optional[float] = 0.0
    sprayed_fluid_l: Optional[float] = 0.0
    target_fluid_density_lpha: Optional[float] = None
    cultivation_method: Optional[str] = None

class TelemetryPoint(BaseModel):
    mission_id: int
    timestamp: datetime
    latitude: float
    longitude: float
    speed_mps: Optional[float] = None
    spray_pressure_bar: Optional[float] = None
    flow_rate_lpm: Optional[float] = None
    raw_status_json: Optional[Dict[str, Any]] = None

# --- 3. UC3 & UC4: Monitoring ---

class MonitoringObservationCreate(BaseModel):
    robot_id: int
    field_id: int
    timestamp: datetime
    latitude: float
    longitude: float
    altitude_m: Optional[float] = None
    avg_foliage_area_cm2: Optional[float] = None
    avg_ndvi: Optional[float] = None
    avg_volume_cm3: Optional[float] = None
    raw_data_json: Optional[Dict[str, Any]] = None

# --- 4. UC5 & UC6: Orchards ---

class TreeCreate(BaseModel):
    field_id: int
    tree_identifier: str
    variety: Optional[str] = None
    planting_date: Optional[date] = None
    latitude: float
    longitude: float

class ImageUploadRequest(BaseModel):
    tree_id: int
    filename: str
    content_type: str = "image/jpeg"

class ImageDetection(BaseModel):
    # This ID links to the uploaded image in the DB
    # The user gets this ID after confirming the upload
    class_name: str
    confidence: float
    x: float
    y: float
    width: float
    height: float
