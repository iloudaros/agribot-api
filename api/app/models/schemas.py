import uuid
from pydantic import BaseModel, Field
from datetime import datetime

class MissionCreate(BaseModel):
    robot_id: int
    field_id: int
    mission_type: str
    start_time: datetime
    end_time: datetime
    travelled_distance_m: float | None = None
    covered_area_m2: float | None = None
    sprayed_fluid_l: float | None = None
    target_fluid_density_lpha: float | None = None
    setpoint_pressure_bar: float | None = None
    cultivation_method: str | None = None
    inference_model: str | None = None
    context_crop_id: int | None = None
    target_id: int | None = None
    min_latitude: float | None = None
    max_latitude: float | None = None
    min_longitude: float | None = None
    max_longitude: float | None = None
    crop_weed_correlation: float | None = None
    weed_liquid_correlation: float | None = None

class Mission(MissionCreate):
    id: int
    user_id: int | None = None
    created_at: datetime

class RobotState(BaseModel):
    timestamp: datetime
    system_state: str | None = None
    latitude_rad: float | None = None
    longitude_rad: float | None = None
    pose_x_m: float | None = None
    pose_y_m: float | None = None
    pose_theta_rad: float | None = None
    speed_x_mps: float | None = None
    speed_y_mps: float | None = None
    speed_omega_radps: float | None = None
    unit0_fluid_l: float | None = None
    unit1_fluid_l: float | None = None
    unit2_fluid_l: float | None = None
    target_coverage_percent: float | None = None
    avoid_coverage_percent: float | None = None

class AgriEvent(BaseModel):
    timestamp: datetime
    latitude: float
    longitude: float
    altitude: float | None = None
    event_type: str
    event_value: float

class ImagePrediction(BaseModel):
    detection_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    class_name: str = Field(alias="class")
    confidence: float
    x: float
    y: float
    width: float
    height: float

class MissionImage(BaseModel):
    id: int
    mission_id: int
    timestamp: datetime
    image_url: str
    latitude: float | None = None
    longitude: float | None = None
    camera_id: int | None = None
