from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum

# ===== ENUMS =====

class TransferStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    COURIER_ASSIGNED = "courier_assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DELIVERY_FAILED = "delivery_failed"
    RECEPTION_ISSUES = "reception_issues"

class Purpose(str, Enum):
    CLIENTE = "cliente"
    RESTOCK = "restock"

class PickupType(str, Enum):
    SELLER = "seller"
    CORREDOR = "corredor"

class DestinationType(str, Enum):
    BODEGA = "bodega"
    EXHIBICION = "exhibicion"

# ===== REQUEST SCHEMAS =====

class TransferRequestCreate(BaseModel):
    """Schema para crear solicitud de transferencia - VE003"""
    source_location_id: int = Field(..., description="ID de ubicación origen")
    sneaker_reference_code: str = Field(..., min_length=1, description="Código de referencia del producto")
    brand: str = Field(..., min_length=1, description="Marca del producto")
    model: str = Field(..., min_length=1, description="Modelo del producto")
    size: str = Field(..., min_length=1, description="Talla solicitada")
    quantity: int = Field(..., gt=0, description="Cantidad solicitada")
    purpose: Purpose = Field(..., description="Propósito: cliente presente o restock")
    pickup_type: PickupType = Field(default=PickupType.CORREDOR, description="Tipo de recolección")
    destination_type: DestinationType = Field(default=DestinationType.BODEGA, description="Tipo de destino")
    notes: Optional[str] = Field(None, max_length=500, description="Notas adicionales")

class TransferAcceptance(BaseModel):
    """Schema para aceptar/rechazar transferencia - BG002"""
    transfer_request_id: int = Field(..., gt=0)
    accepted: bool = Field(..., description="True para aceptar, False para rechazar")
    estimated_preparation_time: int = Field(default=30, ge=5, le=120, description="Tiempo estimado en minutos")
    notes: Optional[str] = Field(None, max_length=500, description="Notas del bodeguero")

class CourierAcceptance(BaseModel):
    """Schema para que corredor acepte transporte - CO002"""
    estimated_pickup_time: int = Field(default=20, ge=5, le=60, description="Tiempo estimado para llegar en minutos")
    notes: Optional[str] = Field(None, max_length=300, description="Notas del corredor")

class PickupConfirmation(BaseModel):
    """Schema para confirmar recolección - CO003"""
    pickup_notes: Optional[str] = Field(None, max_length=300, description="Notas de la recolección")

class DeliveryConfirmation(BaseModel):
    """Schema para confirmar entrega - CO004"""
    delivery_successful: bool = Field(default=True, description="Si la entrega fue exitosa")
    notes: Optional[str] = Field(None, max_length=300, description="Notas de la entrega")

class ReceptionConfirmation(BaseModel):
    """Schema para confirmar recepción - VE008"""
    received_quantity: int = Field(..., gt=0, description="Cantidad recibida")
    condition_ok: bool = Field(default=True, description="Si el producto llegó en buen estado")
    notes: Optional[str] = Field(None, max_length=300, description="Notas de recepción")

class TransportIncidentCreate(BaseModel):
    """Schema para reportar incidencia - CO005"""
    incident_type: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)

# ===== RESPONSE SCHEMAS =====

class LocationInfo(BaseModel):
    """Información básica de ubicación"""
    id: int
    name: str
    type: str
    address: Optional[str] = None

class UserInfo(BaseModel):
    """Información básica de usuario"""
    id: int
    first_name: str
    last_name: str
    email: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

class ProductInfo(BaseModel):
    """Información del producto en transferencia"""
    reference_code: str
    brand: str
    model: str
    size: str
    quantity: int
    color: Optional[str] = None
    image_url: Optional[str] = None
    unit_price: Optional[float] = None

class TransferRequestResponse(BaseModel):
    """Response completo de transferencia"""
    id: int
    status: TransferStatus
    purpose: Purpose
    pickup_type: PickupType
    destination_type: DestinationType
    
    # Información del producto
    product_info: ProductInfo
    
    # Ubicaciones
    source_location: LocationInfo
    destination_location: LocationInfo
    
    # Participantes
    requester: UserInfo
    warehouse_keeper: Optional[UserInfo] = None
    courier: Optional[UserInfo] = None
    
    # Timestamps
    requested_at: datetime
    accepted_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    confirmed_reception_at: Optional[datetime] = None
    
    # Notas y estimaciones
    notes: Optional[str] = None
    reception_notes: Optional[str] = None
    estimated_pickup_time: Optional[int] = None
    
    # Información de estado
    can_cancel: bool = False
    can_accept: bool = False
    can_pickup: bool = False
    can_deliver: bool = False
    can_confirm_reception: bool = False
    
    class Config:
        from_attributes = True

class TransferStatusInfo(BaseModel):
    """Información detallada del estado"""
    status: TransferStatus
    title: str
    description: str
    detail: str
    action_required: Optional[str] = None
    next_step: str
    estimated_time: Optional[str] = None
    urgency: str  # "high", "medium", "normal"
    can_cancel: bool = False
    progress_percentage: int = 0

class TransferSummary(BaseModel):
    """Resumen de transferencias"""
    total_requests: int
    pending: int
    accepted: int
    in_transit: int
    delivered: int
    completed: int
    cancelled: int

class TransferDashboard(BaseModel):
    """Dashboard de transferencias por rol"""
    transfers: List[TransferRequestResponse]
    summary: TransferSummary
    attention_needed: List[dict]
    user_info: dict
    last_updated: datetime

# ===== SCHEMAS PARA FILTROS =====

class TransferFilters(BaseModel):
    """Filtros para búsqueda de transferencias"""
    status: Optional[List[TransferStatus]] = None
    purpose: Optional[Purpose] = None
    source_location_id: Optional[int] = None
    destination_location_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    requester_id: Optional[int] = None
    warehouse_keeper_id: Optional[int] = None
    courier_id: Optional[int] = None

class TransferMetrics(BaseModel):
    """Métricas de transferencias"""
    total_requests: int
    completion_rate: float
    average_processing_time: float
    urgent_requests: int
    failed_deliveries: int
    top_requested_products: List[dict]