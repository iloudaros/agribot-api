from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field as PydanticField


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
# PC2 Schemas #
###############

# -- Ecorobotix --
class PC2EcoGeoJSONUploadRequest(BaseModel):
    mission_id: int
    filename: str = "mission.geojson"

class PC2EcoGeoTIFFUploadRequest(BaseModel):
    mission_id: int
    filename: str = "map.tif"

class PC2EcoConfirmGeoJSON(BaseModel):
    geojson_uri: str

class PC2EcoConfirmGeoTIFF(BaseModel):
    geotiff_uri: str

class PC2EcorobotixMission(BaseModel):
    mission_id: int
    geojson_uri: Optional[str] = None
    geotiff_uri: Optional[str] = None


# -- DTI Drones --
class PC2DTIPhotoUploadRequest(BaseModel):
    mission_id: int
    filename: str = "drone_photo.jpg"

class PC2DTIPhotoConfirm(BaseModel):
    photo_uri: str

class PC2DTIPhotoResponse(BaseModel):
    mission_id: int
    photo_uri: str
    created_at: datetime

class PC2DTILatestPhotoResponse(BaseModel):
    mission_id: int
    field_id: int
    photo_url: str
    created_at: datetime



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
    suggested_fertilization: Optional[float] = None 
    chosen_fertilization: Optional[float] = None     



class PC3InspectionBatch(BaseModel):
    mission_id: int
    data: List[PC3InspectionItem]



###############
# PC4 Schemas #
###############
class PC4ChannelData(BaseModel):
    channelName: str
    biomass: float
    fruitQuality: float
    growthInsight: float

class PC4MonitoringPayload(BaseModel):
    parcel_id: Optional[int] = None
    date: Optional[str] = None
    channels: List[PC4ChannelData]




###############
# PC5 Schemas #
###############

class PC5Context(BaseModel):
    PO: Optional[str] = None
    AGRO: Optional[str] = None
    PATO: Optional[str] = None
    CO_370: Optional[str] = None
    TreeID: Optional[str] = None
    Variety: Optional[str] = None
    Rootstock: Optional[str] = None
    PlantingDate: Optional[str] = None
    FruitCount: Optional[str] = None

class PC5TreeMetadata(BaseModel):
    TreeID: str
    Variety: Optional[str] = None
    Rootstock: Optional[str] = None
    PlantingDate: Optional[int] = None

class PC5Grid(BaseModel):
    row: Optional[int] = PydanticField(None, alias="AGRO:00000155")
    col: Optional[int] = PydanticField(None, alias="PATO:0000140")
    model_config = ConfigDict(populate_by_name=True)

class PC5Geolocation(BaseModel):
    lat: Optional[float] = PydanticField(None, alias="AGRO:00000574")
    lon: Optional[float] = PydanticField(None, alias="AGRO:00000575")
    elevation: Optional[float] = PydanticField(None, alias="AGRO:00000612")
    model_config = ConfigDict(populate_by_name=True)

class PC5Location(BaseModel):
    grid: Optional[PC5Grid] = None
    geolocation: Optional[PC5Geolocation] = None

class PC5YoloDetection(BaseModel):
    picture_id: str
    class_id: int
    x: float
    y: float
    width: float
    height: float
    confidence: float

class PC5Apple(BaseModel):
    AppleID: str
    SizeClass: Optional[str] = None
    OvercolorClass: Optional[str] = None
    yolo_detection: PC5YoloDetection

class PC5HarvestData(BaseModel):
    FruitCount: int
    apples: List[PC5Apple] = []

class PC5Tree(BaseModel):
    tree_metadata: PC5TreeMetadata
    location: Optional[PC5Location] = None
    harvest_data: PC5HarvestData

class PC5Payload(BaseModel):
    context: Optional[PC5Context] = PydanticField(None, alias="@context")
    trees: List[PC5Tree]
    model_config = ConfigDict(populate_by_name=True)



###############
# PC6 Schemas #
###############

class PC6YoloDetection(BaseModel):
    picture_id: str
    class_id: int
    x: float
    y: float
    width: float
    height: float
    confidence: float

class PC6Branch(BaseModel):
    BranchID: str
    Age_years: Optional[int] = None
    Length_m: Optional[float] = None
    Diameter_cm: Optional[float] = None
    yolo_detection: PC6YoloDetection

class PC6OperationData(BaseModel):
    BranchesToCutCount: Optional[int] = None
    BranchesCutCount: Optional[int] = None
    branches: List[PC6Branch] = []

class PC6Tree(BaseModel):
    tree_metadata: PC5TreeMetadata
    location: Optional[PC5Location] = None
    thinning_data: Optional[PC6OperationData] = None
    pruning_data: Optional[PC6OperationData] = None

class PC6Payload(BaseModel):
    context: Optional[dict] = PydanticField(default=None, alias="@context")
    trees: List[PC6Tree]
    model_config = ConfigDict(populate_by_name=True)