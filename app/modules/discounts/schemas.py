# app/modules/discounts/schemas.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime
from app.shared.schemas.common import BaseResponse

class DiscountRequestCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, le=5000, description="Monto del descuento (máximo $5,000)")
    reason: str = Field(..., min_length=10, max_length=500, description="Razón del descuento")
    
    @validator('reason')
    def validate_reason(cls, v):
        if not v.strip():
            raise ValueError('La razón no puede estar vacía')
        return v.strip()

class DiscountRequestResponse(BaseResponse):
    discount_request_id: int
    amount: Decimal
    reason: str
    status: str
    requested_at: datetime
    seller_info: Dict[str, Any]
    within_limit: bool
    max_allowed: int = 5000

class MyDiscountRequestsResponse(BaseResponse):
    requests: List[Dict[str, Any]]
    summary: Dict[str, Any]
    seller_info: Dict[str, Any]

class DiscountRequest(BaseModel):
    """Modelo de solicitud de descuento"""
    id: int
    seller_id: int
    amount: Decimal
    reason: str
    status: str
    administrator_id: Optional[int]
    requested_at: datetime
    reviewed_at: Optional[datetime]
    admin_comments: Optional[str]
    
    # Información adicional para response
    admin_first_name: Optional[str] = None
    admin_last_name: Optional[str] = None