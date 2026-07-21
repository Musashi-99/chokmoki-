from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# Lifecycle keys the alert handlers (src/alerts/handlers.py) know how to
# fire. "otp_login" is documented-only — OTP delivery goes through MSG91's
# dedicated OTP API (send_otp/verify_otp), not the Flow/template API these
# rows configure.
LIFECYCLE_TEMPLATE_KEYS = [
    "order_placed",
    "order_shipped",
    "order_out_for_delivery",
    "order_delivered",
    "order_cancelled",
]


class SmsTemplate(BaseModel):
    key: str
    msg91_template_id: Optional[str] = None
    sender_id_override: Optional[str] = None
    variables: List[str] = Field(default_factory=list)
    enabled: bool = False
    description: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[str] = None

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


class SmsTemplateUpdate(BaseModel):
    msg91_template_id: Optional[str] = None
    sender_id_override: Optional[str] = None
    variables: Optional[List[str]] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
