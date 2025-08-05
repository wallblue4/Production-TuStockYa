from pydantic import BaseModel, Field, ConfigDict, field_validator, FieldValidationInfo
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum

# ==================== ENUMS ====================

class PaymentMethodType(str, Enum):
    efectivo = "efectivo"
    tarjeta = "tarjeta"
    transferencia = "transferencia"
    nequi = "nequi"
    daviplata = "daviplata"
    mixto = "mixto"

class ReservationPurpose(str, Enum):
    cliente = "cliente"
    restock = "restock"

class SaleStatus(str, Enum):
    completed = "completed"
    pending_confirmation = "pending_confirmation"
    cancelled = "cancelled"

# ==================== CLASE BASE PARA RESPUESTAS (Pydantic v2) ====================

class SalesBaseModel(BaseModel):
    """
    Clase base para todos los esquemas de respuesta,
    con configuración de Pydantic v2.
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            Decimal: float,
            datetime: lambda v: v.isoformat(),
        }
    )

# ==================== REQUEST SCHEMAS ====================

class PaymentMethodRequest(BaseModel):
    type: PaymentMethodType
    amount: float = Field(..., gt=0, description="Monto del método de pago")
    reference: Optional[str] = Field(None, description="Referencia (últimos 4 dígitos tarjeta, etc.)")

class SaleItemRequest(BaseModel):
    sneaker_reference_code: str = Field(..., description="Código de referencia del producto")
    brand: str = Field(..., description="Marca del producto")
    model: str = Field(..., description="Modelo del producto")
    color: Optional[str] = Field(None, description="Color del producto")
    size: str = Field(..., description="Talla")
    quantity: int = Field(..., gt=0, description="Cantidad")
    unit_price: float = Field(..., gt=0, description="Precio unitario")
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v: int):
        if v <= 0:
            raise ValueError('La cantidad debe ser mayor a 0')
        return v

class SaleCreateRequest(BaseModel):
    items: List[SaleItemRequest] = Field(..., min_items=1, description="Items de la venta")
    total_amount: float = Field(..., gt=0, description="Monto total de la venta")
    payment_methods: List[PaymentMethodRequest] = Field(..., min_items=1, description="Métodos de pago")
    notes: Optional[str] = Field("", description="Notas adicionales")
    requires_confirmation: bool = Field(False, description="Si requiere confirmación posterior")
    
    @field_validator('payment_methods')
    @classmethod
    def validate_payment_total(cls, v: List[PaymentMethodRequest], info: FieldValidationInfo):
        if 'total_amount' in info.data:
            total_payments = sum(p.amount for p in v)
            if abs(total_payments - info.data['total_amount']) > 0.01:
                raise ValueError(f"Los métodos de pago ({total_payments}) no coinciden con el total ({info.data['total_amount']})")
        return v

class ExpenseCreateRequest(BaseModel):
    concept: str = Field(..., description="Concepto del gasto")
    amount: float = Field(..., gt=0, description="Monto del gasto")
    notes: Optional[str] = Field("", description="Notas adicionales")

class DiscountRequestCreate(BaseModel):
    amount: float = Field(..., gt=0, le=5000, description="Monto del descuento (máximo $5,000)")
    reason: str = Field(..., min_length=10, description="Razón del descuento")

class ProductReservationRequest(BaseModel):
    reference_code: str = Field(..., description="Código de referencia del producto")
    size: str = Field(..., description="Talla")
    quantity: int = Field(1, gt=0, description="Cantidad a reservar")
    purpose: ReservationPurpose = Field(..., description="Propósito de la reserva")
    notes: Optional[str] = Field("", description="Notas adicionales")

# ==================== RESPONSE SCHEMAS ====================

class SaleItemResponse(SalesBaseModel):
    id: int
    sneaker_reference_code: str
    brand: str
    model: str
    color: Optional[str]
    size: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

class PaymentMethodResponse(SalesBaseModel):
    id: int
    payment_type: str
    amount: Decimal
    reference: Optional[str]
    created_at: datetime

class SaleResponse(SalesBaseModel):
    id: int
    seller_id: int
    location_id: int
    total_amount: Decimal
    receipt_image: Optional[str]
    sale_date: datetime
    status: str
    notes: Optional[str]
    requires_confirmation: bool
    confirmed: bool
    confirmed_at: Optional[datetime]
    
    # Relacionados
    items: List[SaleItemResponse]
    payments: List[PaymentMethodResponse]
    
    # Información adicional
    seller_info: Dict[str, Any]
    status_info: Dict[str, Any]

class ExpenseResponse(SalesBaseModel):
    id: int
    user_id: int
    location_id: int
    concept: str
    amount: Decimal
    receipt_image: Optional[str]
    expense_date: datetime
    notes: Optional[str]
    
    # Información adicional
    user_info: Dict[str, Any]
    has_receipt: bool

class DiscountRequestResponse(SalesBaseModel):
    id: int
    seller_id: int
    amount: Decimal
    reason: str
    status: str
    administrator_id: Optional[int]
    requested_at: datetime
    reviewed_at: Optional[datetime]
    admin_comments: Optional[str]
    
    # Información adicional
    status_info: Dict[str, Any]

class ProductAvailabilityInfo(SalesBaseModel):
    physical_stock: int
    reserved_quantity: int
    available_stock: int
    can_fulfill: bool

class ProductLocationInfo(SalesBaseModel):
    location_id: int
    location_name: str
    location_type: str
    location_address: Optional[str]

class ProductStockInfo(SalesBaseModel):
    size: str
    quantity_stock: int
    quantity_exhibition: int
    location: ProductLocationInfo

class ProductInfoResponse(SalesBaseModel):
    reference_code: str
    brand: str
    model: str
    description: str
    color: Optional[str]
    unit_price: Decimal
    box_price: Decimal
    image_url: Optional[str]
    
    # Stock por ubicación
    current_location_stock: List[ProductStockInfo]
    other_locations_stock: List[ProductStockInfo]
    
    # Disponibilidad
    availability: ProductAvailabilityInfo
    
    # Transferencias
    can_request_transfer: bool
    estimated_transfer_time: Optional[str]

class ProductScanResponse(SalesBaseModel):
    success: bool
    scan_timestamp: datetime
    scanned_by: Dict[str, Any]
    
    # Resultados del escaneo
    best_match: Optional[ProductInfoResponse]
    alternative_matches: List[ProductInfoResponse]
    total_matches_found: int
    
    # Disponibilidad resumen
    availability_summary: Dict[str, Any]
    
    # Procesamiento
    processing_time_ms: float
    image_info: Dict[str, Any]
    classification_service: Dict[str, Any]

class DailySalesResponse(SalesBaseModel):
    success: bool
    date: str
    sales: List[SaleResponse]
    
    # Estadísticas del día
    summary: Dict[str, Any] = Field(..., description="Estadísticas consolidadas del día")

class ProductReservationResponse(SalesBaseModel):
    id: int
    sneaker_reference_code: str
    size: str
    quantity: int
    user_id: int
    location_id: int
    purpose: str
    status: str
    reserved_at: datetime
    expires_at: datetime
    released_at: Optional[datetime]
    
    # Información calculada
    time_left_seconds: int
    time_left_minutes: float

class VendorDashboardResponse(SalesBaseModel):
    success: bool
    dashboard_timestamp: datetime
    vendor_info: Dict[str, Any]
    
    # Resumen del día
    today_summary: Dict[str, Any]
    
    # Acciones pendientes
    pending_actions: Dict[str, Any]
    
    # Acciones rápidas disponibles
    quick_actions: List[str]

# ==================== SCHEMAS DE TRANSFERENCIAS Y ALTERNATIVAS ====================

class AlternativeProductResponse(SalesBaseModel):
    reference_code: str
    brand: str
    model: str
    size: str
    available_quantity: int
    unit_price: Decimal
    location: str
    similarity_reason: str

class TransferRequestResponse(SalesBaseModel):
    transfer_request_id: int
    message: str
    status: str
    estimated_time: str
    next_steps: List[str]

class ProductSearchResponse(SalesBaseModel):
    success: bool
    reference_code: str
    products_found: List[ProductInfoResponse]
    alternative_suggestions: List[AlternativeProductResponse]
    can_request_transfer: bool
    searched_by: Dict[str, Any]

# ==================== VALIDADORES COMUNES ====================

class CommonValidators:
    @staticmethod
    def validate_positive_amount(v): # Se elimina cls
        if v <= 0:
            raise ValueError('El monto debe ser mayor a 0')
        return v
    
    @staticmethod
    def validate_non_empty_string(v): # Se elimina cls
        if not v or not v.strip():
            raise ValueError('Este campo no puede estar vacío')
        return v.strip()
    
    @staticmethod
    def validate_reference_code(v): # Se elimina cls
        if not v or len(v) < 3:
            raise ValueError('Código de referencia debe tener al menos 3 caracteres')
        return v.upper().strip()