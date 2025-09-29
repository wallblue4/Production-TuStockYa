# app/modules/sales_new/schemas.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
from app.shared.schemas.common import BaseResponse

class SaleItem(BaseModel):
    sneaker_reference_code: str = Field(..., description="Código de referencia del producto")
    brand: str = Field(..., description="Marca del producto")
    model: str = Field(..., description="Modelo del producto")
    color: Optional[str] = Field(None, description="Color del producto")
    size: str = Field(..., description="Talla del producto")
    quantity: int = Field(..., gt=0, description="Cantidad vendida")
    unit_price: Decimal = Field(..., gt=0, description="Precio unitario")
    
    @property
    def subtotal(self) -> Decimal:
        return self.quantity * self.unit_price

class PaymentMethod(BaseModel):
    type: str = Field(..., description="Tipo: efectivo, tarjeta, transferencia, mixto")
    amount: Decimal = Field(..., gt=0, description="Monto del pago")
    reference: Optional[str] = Field(None, description="Referencia del pago")

class SaleCreateRequest(BaseModel):
    items: List[SaleItem] = Field(..., min_items=1, description="Items de la venta")
    total_amount: Decimal = Field(..., gt=0, description="Monto total")
    payment_methods: List[PaymentMethod] = Field(..., min_items=1, description="Métodos de pago")
    notes: Optional[str] = Field(None, max_length=500, description="Notas adicionales")
    requires_confirmation: bool = Field(False, description="Requiere confirmación posterior")
    
    @validator('payment_methods')
    def validate_payment_total(cls, v, values):
        if 'total_amount' in values:
            payment_total = sum(payment.amount for payment in v)
            if abs(payment_total - values['total_amount']) > Decimal('0.01'):
                raise ValueError('La suma de pagos debe coincidir con el total')
        return v

class SaleResponse(BaseResponse):
    sale_id: int
    total_amount: Decimal
    status: str
    requires_confirmation: bool
    created_at: datetime
    items_count: int
    payment_methods_count: int
    inventory_updated: bool

class SaleConfirmationRequest(BaseModel):
    sale_id: int = Field(..., description="ID de la venta")
    confirmed: bool = Field(..., description="Confirmación de la venta")
    confirmation_notes: Optional[str] = Field(None, max_length=500, description="Notas de confirmación")

class DailySalesResponse(BaseResponse):
    date: str
    sales: List[Dict[str, Any]]
    summary: Dict[str, Any]
    seller_info: Dict[str, Any]

class PendingSalesResponse(BaseResponse):
    pending_sales: List[Dict[str, Any]]
    count: int
    total_pending_amount: Decimal