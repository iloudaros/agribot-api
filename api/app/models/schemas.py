from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field as PydanticField


MissionStatus = Literal["ongoing", "complete", "canceled", "aborted"]
SprayingMissionType = Literal["pc1_inspection", "pc1_spraying", "pc2_spraying"]
PC1MissionStatus = Literal["ongoing", "inspection_complete", "spraying_complete", "aborted"]


###############################
# Core Infrastructure Schemas #
###############################
class UserCreate(BaseModel):
    id: int
    email: str
    password: str
    name: Optional[str] = None
    role: str = "farmer"
    is_active: bool = True


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool


class FieldOwner(BaseModel):
    user_id: int
    ownership_percentage: float


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: List[List[List[float]]]


class FieldCreate(BaseModel):
    name: str
    crop_name: Optional[str] = None
    shape: Optional[GeoJSONPolygon] = None


class FieldBatchCreate(BaseModel):
    name: str
    crop_name: Optional[str] = None
    shape: Optional[GeoJSONPolygon] = None


class Field(BaseModel):
    id: int
    name: str
    crop_name: Optional[str] = None
    shape: Optional[GeoJSONPolygon] = None
    owners: List[FieldOwner] = PydanticField(default_factory=list)


class FieldOwnershipCreate(BaseModel):
    field_id: int
    user_id: int
    ownership_percentage: float


class FieldOwnershipBatchCreate(BaseModel):
    items: List[FieldOwnershipCreate]


###################
# Mission Schemas #
###################
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


class Mission(MissionBase):
    id: int
    commander_id: int
    field_id: int
    mission_type: str
    status: MissionStatus
    start_time: datetime
    end_time: Optional[datetime] = None


class MissionCreate(MissionBase):
    id: Optional[int] = None


###############
# PC1 Schemas #
###############
class PC1MissionState(BaseModel):
    mission_id: int
    status: PC1MissionStatus


class WeedUpdate(BaseModel):
    is_sprayed: bool
    spray_time: Optional[datetime] = None
    verified: Optional[bool] = None


class WeedCreate(BaseModel):
    id: int
    inspection_id: int
    name: Optional[str] = None
    image: Optional[str] = None
    confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    needs_verification: bool = False
    verified: Optional[bool] = None
    is_sprayed: bool = False
    spray_time: Optional[datetime] = None


class WeedBatchUpdateItem(BaseModel):
    id: int
    inspection_id: int
    is_sprayed: bool
    spray_time: Optional[datetime] = None
    verified: Optional[bool] = None


class Weed(BaseModel):
    id: int
    inspection_id: int
    name: Optional[str] = None
    image: Optional[str] = None
    confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    needs_verification: bool = False
    verified: Optional[bool] = None
    is_sprayed: bool
    spray_time: Optional[datetime] = None


class PC1ImageUploadRequest(BaseModel):
    filename: str
    inspection_id: int


###############
# PC3 Schemas #
###############
class PC3InspectionItem(BaseModel):
    timestamp_unix: float
    latitude: float
    longitude: float
    biomass: Optional[float] = None
    altitude_m: Optional[float] = None
    avg_dim_x_cm: Optional[float] = None
    avg_dim_y_cm: Optional[float] = None
    avg_dim_z_cm: Optional[float] = None
    avg_volume_cm3: Optional[float] = None
    avg_fol_area_cm2: Optional[float] = None
    avg_ndvi: Optional[float] = None
    avg_biomass: Optional[float] = None
    avg_fertilization: Optional[float] = None


class PC3InspectionBatch(BaseModel):
    mission_id: int
    data: List[PC3InspectionItem]
