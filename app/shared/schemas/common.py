# app/shared/schemas/common.py
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal

class BaseResponse(BaseModel):
    success: bool
    message: str = ""
    timestamp: datetime = datetime.now()

class ErrorResponse(BaseResponse):
    success: bool = False
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int

class ProductInfo(BaseModel):
    reference_code: str
    brand: str
    model: str
    color: Optional[str] = None
    description: str
    unit_price: Decimal
    box_price: Decimal
    image_url: Optional[str] = None

class LocationInfo(BaseModel):
    location_id: int
    location_name: str
    location_type: str
    address: Optional[str] = None