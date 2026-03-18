from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field as PydanticField


MissionStatus = Literal["ongoing", "complete", "canceled", "aborted"]
SprayingMissionType = Literal["pc1_inspection", "pc1_spraying", "pc2_spraying"]
PC1MissionStatus = Literal["ongoing", "inspection_complete", "spraying_complete", "aborted"]

# Core Infrastructure Schemas
class UserCreate(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    surname: Optional[str] = None
    role: str = "farmer"  # defaults to farmer
    is_active: bool = True

class UserResponse(BaseModel):
    id: int
    username: str
    name: Optional[str] = None
    surname: Optional[str] = None
    role: str
    is_active: bool

class FarmOwner(BaseModel):
    user_id: int
    ownership_percentage: float


class FarmCreate(BaseModel):
    name: str
    center_lat: float
    center_lon: float
    ownership_percentage: float = 100.0

class FarmBatchCreate(BaseModel):
    name: str
    center_lat: float
    center_lon: float
    ownership_percentage: float = 100.0
    owner_id: int  

class Farm(BaseModel):
    id: int
    name: str
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    owners: List[FarmOwner] = PydanticField(default_factory=list)


class FieldCreate(BaseModel):
    farm_id: int
    name: str
    crop_name: Optional[str] = None
    boundary_wkt: Optional[str] = None


class Field(BaseModel):
    id: int
    farm_id: int
    name: str
    crop_name: Optional[str] = None
    boundary_wkt: Optional[str] = None


# Mission Schemas
class MissionType(BaseModel):
    id: str
    pilot_case: Optional[str] = None
    partner: Optional[str] = None
    description: Optional[str] = None


class MissionUpdate(BaseModel):
    status: Optional[MissionStatus] = None
    end_time: Optional[datetime] = None


class MissionBase(BaseModel):
    field_id: int
    mission_type: str
    status: MissionStatus = "ongoing"
    start_time: datetime
    mission_date: Optional[datetime] = None


class MissionCreate(MissionBase):
    id: Optional[str] = None


class Mission(MissionBase):
    id: str
    commander_id: int
    end_time: Optional[datetime] = None

class PC1MissionState(BaseModel):
    mission_id: str
    status: PC1MissionStatus


class PC2SprayingMetadata(BaseModel):
    max_lat: Optional[float] = None
    min_lat: Optional[float] = None
    max_long: Optional[float] = None
    min_long: Optional[float] = None
    area_analyzed: Optional[float] = None
    average_density: Optional[float] = None
    crop_weed_correlation: Optional[float] = None
    weed_liquid_correlation: Optional[float] = None

class SprayingMissionCreate(BaseModel):
    id: Optional[str] = None
    field_id: int
    mission_type: SprayingMissionType
    status: MissionStatus = "complete"
    start_time: datetime
    end_time: Optional[datetime] = None
    mission_date: Optional[datetime] = None
    pc2_properties: Optional[Dict[str, Any]] = None
    pc2_metadata: Optional[PC2SprayingMetadata] = None


class SprayingMission(BaseModel):
    id: str
    commander_id: Optional[int] = None
    field_id: Optional[int] = None
    mission_type: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    mission_date: Optional[datetime] = None
    pc2_properties: Optional[Dict[str, Any]] = None
    pc2_metadata: Optional[PC2SprayingMetadata] = None


# PC1 Schemas
class WeedUpdate(BaseModel):
    is_sprayed: bool
    spray_time: Optional[datetime] = None


class WeedCreate(BaseModel):
    id: str  
    inspection_id: str
    name: Optional[str] = None
    image: Optional[str] = None
    confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_sprayed: bool = False
    spray_time: Optional[datetime] = None


class WeedBatchUpdateItem(BaseModel):
    id: str  
    inspection_id: str 
    is_sprayed: bool
    spray_time: Optional[datetime] = None


class Weed(BaseModel):
    id: str 
    inspection_id: str
    name: Optional[str] = None
    image: Optional[str] = None
    confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_sprayed: bool
    spray_time: Optional[datetime] = None








class MonitoringInspectionCreate(BaseModel):
    id: Optional[str] = None
    field_id: int
    status: MissionStatus = "complete"
    start_time: datetime
    end_time: Optional[datetime] = None
    mission_date: Optional[datetime] = None
    latitude: float
    longitude: float
    biomass: Optional[float] = None
    ndvi: Optional[float] = None


class MonitoringInspection(BaseModel):
    id: str
    commander_id: Optional[int] = None
    field_id: Optional[int] = None
    mission_type: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    mission_date: Optional[datetime] = None
    latitude: float
    longitude: float
    biomass: Optional[float] = None
    ndvi: Optional[float] = None
