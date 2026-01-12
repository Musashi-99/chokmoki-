from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from pydantic_core import core_schema
from bson import ObjectId
from datetime import datetime


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            if not ObjectId.is_valid(v):
                raise ValueError("Invalid objectid")
            return ObjectId(v)
        raise ValueError("Invalid objectid")
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, handler):
        field_schema.update(type="string")
        return field_schema


class AnalyticsEvent(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class AnalyticsEventCreate(BaseModel):
    event_type: str
    timestamp: Optional[datetime] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsMetric(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    metric_name: str
    metric_type: str
    value: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    dimensions: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class AnalyticsMetricCreate(BaseModel):
    metric_name: str
    metric_type: str
    value: float
    timestamp: Optional[datetime] = None
    dimensions: Dict[str, Any] = Field(default_factory=dict)
