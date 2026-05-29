from typing import Optional
from pydantic import BaseModel, Field, model_validator
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class ContactSubmission(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    message: str = ""
    note: str = ""
    source: str = "postcard"
    read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }

    @model_validator(mode="after")
    def sync_note_and_message(self):
        message = self.message.strip()
        note = self.note.strip()
        if not message and note:
            self.message = note
            message = note
        if not note and message:
            self.note = message
        return self


class ContactSubmissionCreate(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    message: str = Field(default="", max_length=8000)
    note: str = Field(default="", max_length=8000)
    source: str = "postcard"

    @model_validator(mode="after")
    def validate_message_or_note(self):
        message = self.message.strip()
        note = self.note.strip()
        if not message and note:
            self.message = note
            message = note
        if not note and message:
            self.note = message
        if not message:
            raise ValueError("message is required")
        return self


class NewsletterSubscription(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    email: str
    source: str = "footer"
    read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class NewsletterSubscribeCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    source: str = "footer"
