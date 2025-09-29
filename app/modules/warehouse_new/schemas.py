# app/modules/warehouse_new/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.shared.schemas.common import BaseResponse

class WarehouseRequestAcceptance(BaseModel):
    transfer_request_id: int = Field(..., description="ID de la solicitud")
    accepted: bool = Field(..., description="Si se acepta o rechaza")
    rejection_reason: Optional[str] = Field(None, description="Razón del rechazo")
    estimated_preparation_time: Optional[int] = Field(None, description="Tiempo estimado de preparación en minutos")
    warehouse_notes: Optional[str] = Field(None, description="Notas del bodeguero")

class CourierDelivery(BaseModel):
    transfer_request_id: int = Field(..., description="ID de la solicitud")
    courier_id: int = Field(..., description="ID del corredor")
    delivery_notes: Optional[str] = Field(None, description="Notas de entrega")

class PendingRequestsResponse(BaseResponse):
    pending_requests: List[Dict[str, Any]]
    count: int
    breakdown: Dict[str, Any]
    warehouse_keeper: str

class AcceptedRequestsResponse(BaseResponse):
    accepted_requests: List[Dict[str, Any]]
    count: int
    warehouse_info: Dict[str, Any]

class InventoryByLocationResponse(BaseResponse):
    location_info: Dict[str, Any]
    inventory: List[Dict[str, Any]]
    summary: Dict[str, Any]

class RequestInfo(BaseModel):
    id: int
    status: str
    request_type: str
    sneaker_reference_code: str
    brand: str
    model: str
    size: str
    quantity: int
    purpose: str
    requester_name: str
    location_info: Dict[str, Any]
    requested_at: datetime
    urgent_action: bool
    priority_level: str
    time_elapsed: str
    estimated_pickup_time: Optional[str] = None