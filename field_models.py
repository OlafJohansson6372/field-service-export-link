from datetime import date
from enum import Enum
from typing import List

from pydantic import BaseModel, EmailStr, Field


class DispatchStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class FollowUpStatus(str, Enum):
    needs_follow_up = "needs_follow_up"
    closed = "closed"


class WorkOrderPhotoBatch(BaseModel):
    work_order_id: str = Field(min_length=1)
    dispatch_status: DispatchStatus
    photo_keys: List[str]
    technician_note: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    scheduled_date: date


class ExportRequest(BaseModel):
    export_id: str = Field(min_length=1)
    requested_by: EmailStr
    work_orders: List[WorkOrderPhotoBatch]


class ExportItemResult(BaseModel):
    work_order_id: str
    follow_up_status: FollowUpStatus


class ExportResponse(BaseModel):
    export_id: str
    bucket: str
    csv_key: str
    pdf_key: str
    csv_download_url: str
    pdf_download_url: str
    items: List[ExportItemResult]
