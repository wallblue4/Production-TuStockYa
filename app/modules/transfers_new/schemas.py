# app/modules/transfers_new/schemas.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime
from enum import Enum
from app.shared.schemas.common import BaseResponse

class TransferRequestCreate(BaseModel):
    source_location_id: int = Field(..., description="ID de ubicación origen")
    destination_location_id: int = Field(..., description="ID de ubicación destino")
    sneaker_reference_code: str = Field(..., description="Código de referencia del producto")
    brand: str = Field(..., description="Marca del producto")
    model: str = Field(..., description="Modelo del producto")
    size: str = Field(..., description="Talla del producto")
    quantity: int = Field(..., gt=0, description="Cantidad a transferir")
    purpose: str = Field(..., description="Propósito: cliente, restock, exhibition")
    pickup_type: str = Field(..., description="Tipo de recogida: vendedor, corredor")
    destination_type: str = Field(default="bodega", description="Tipo destino: bodega, exhibicion")
    notes: Optional[str] = Field(None, max_length=500, description="Notas adicionales")

class TransferRequestResponse(BaseResponse):
    transfer_request_id: int
    status: str
    estimated_time: str
    priority: str
    next_steps: List[str]
    reservation_expires_at: Optional[str] = None

class MyTransferRequestsResponse(BaseResponse):
    my_requests: List[Dict[str, Any]]
    summary: Dict[str, Any]
    vendor_info: Dict[str, Any]
    workflow_info: Dict[str, Any]

class ReceptionConfirmation(BaseModel):
    received_quantity: int = Field(..., gt=0, description="Cantidad recibida")
    condition_ok: bool = Field(..., description="Condición del producto OK")
    notes: str = Field("", description="Notas de recepción")