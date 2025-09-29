# app/modules/vendor/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime, date
from app.shared.schemas.common import BaseResponse

class VendorDashboardResponse(BaseResponse):
    dashboard_timestamp: datetime
    vendor_info: Dict[str, Any]
    today_summary: Dict[str, Any]
    pending_actions: Dict[str, Any]
    quick_actions: List[str]

class TransferSummaryResponse(BaseResponse):
    pending_transfers: List[Dict[str, Any]]
    urgent_count: int
    normal_count: int
    total_pending: int
    summary: Optional[Dict[str, Any]] = None
    attention_needed: Optional[List[Dict[str, Any]]] = None

class CompletedTransfersResponse(BaseResponse):
    date: str
    completed_transfers: List[Dict[str, Any]]
    today_stats: Dict[str, Any]

class VendorInfo(BaseModel):
    name: str
    email: str
    role: str
    location_id: int
    location_name: str

class TodaySummary(BaseModel):
    date: str
    sales: Dict[str, Any]
    payment_methods_breakdown: List[Dict[str, Any]]
    expenses: Dict[str, Any]
    net_income: float

class PendingActions(BaseModel):
    sale_confirmations: int
    transfer_requests: Dict[str, int]
    discount_requests: Dict[str, int]
    return_notifications: int