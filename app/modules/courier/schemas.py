# app/modules/courier/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.shared.schemas.common import BaseResponse

class CourierAcceptance(BaseModel):
    estimated_pickup_time: int = Field(20, description="Tiempo estimado en minutos para llegar")
    notes: Optional[str] = Field("", description="Notas del corredor")

class PickupConfirmation(BaseModel):
    pickup_notes: Optional[str] = Field("", description="Notas de recolección")

class DeliveryConfirmation(BaseModel):
    delivery_successful: bool = Field(True, description="Si la entrega fue exitosa")
    notes: Optional[str] = Field("", description="Notas de entrega")
    damaged_items: int = Field(0, description="Cantidad de items dañados")

class TransportIncidentReport(BaseModel):
    incident_type: str = Field(..., description="Tipo de incidencia")
    description: str = Field(..., min_length=10, description="Descripción de la incidencia")

class AvailableRequestsResponse(BaseResponse):
    available_requests: List[Dict[str, Any]]
    count: int
    breakdown: Dict[str, Any]
    courier_info: Dict[str, Any]

class MyTransportsResponse(BaseResponse):
    my_transports: List[Dict[str, Any]]
    count: int
    courier_stats: Dict[str, Any]

class DeliveryHistoryResponse(BaseResponse):
    recent_deliveries: List[Dict[str, Any]]
    today_stats: Dict[str, Any]
    performance_metrics: Dict[str, Any]

class CourierRequest(BaseModel):
    id: int
    status: str
    request_type: str
    sneaker_reference_code: str
    brand: str
    model: str
    size: str
    quantity: int
    purpose: str
    action_required: str
    status_description: str
    urgency: str
    transport_info: Dict[str, Any]
    product_image: Optional[str] = None
    priority_score: float = 0.0