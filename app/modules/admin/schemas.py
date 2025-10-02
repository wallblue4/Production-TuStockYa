# app/modules/admin/schemas.py
from pydantic import BaseModel, Field, EmailStr, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class UserRole(str, Enum):
    """Roles de usuario que puede crear el administrador"""
    VENDEDOR = "seller"
    BODEGUERO = "bodeguero"
    CORREDOR = "corredor"

class LocationType(str, Enum):
    """Tipos de ubicación"""
    LOCAL = "local"
    BODEGA = "bodega"

class CostType(str, Enum):
    """Tipos de costo"""
    ARRIENDO = "arriendo"
    SERVICIOS = "servicios"
    NOMINA = "nomina"
    MERCANCIA = "mercancia"
    COMISIONES = "comisiones"
    TRANSPORTE = "transporte"
    OTROS = "otros"

class SaleType(str, Enum):
    """Tipos de venta"""
    DETALLE = "detalle"
    MAYOR = "mayor"

class AlertType(str, Enum):
    """Tipos de alerta"""
    INVENTARIO_MINIMO = "inventario_minimo"
    STOCK_AGOTADO = "stock_agotado"
    PRODUCTO_VENCIDO = "producto_vencido"

class FrequencyType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    UPCOMING = "upcoming"

class ExceptionType(str, Enum):
    SKIP = "skip"
    DIFFERENT_AMOUNT = "different_amount"
    POSTPONED = "postponed"

# ==================== GESTIÓN DE USUARIOS ====================

class UserCreate(BaseModel):
    """Crear usuario (vendedor, bodeguero, corredor)"""
    email: str = Field(..., description="Email único del usuario")
    password: str = Field(..., min_length=6, description="Contraseña (mínimo 6 caracteres)")
    first_name: str = Field(..., min_length=2, description="Nombres")
    last_name: str = Field(..., min_length=2, description="Apellidos")
    role: UserRole = Field(..., description="Rol del usuario")
    location_id: Optional[int] = Field(None, description="Ubicación asignada (opcional)")
    
    @validator('email')
    def validate_email_domain(cls, v):
        # En producción, se podría validar dominio corporativo
        return v.lower()

class UserResponse(BaseModel):
    """Respuesta de usuario creado"""
    id: int
    email: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    location_id: Optional[int]
    location_name: Optional[str]
    is_active: bool
    created_at: datetime

class UserUpdate(BaseModel):
    """Actualizar usuario existente"""
    first_name: Optional[str] = Field(None, min_length=2)
    last_name: Optional[str] = Field(None, min_length=2)
    is_active: Optional[bool] = None
    location_id: Optional[int] = None

class UserAssignment(BaseModel):
    """Asignar usuario a ubicación"""
    user_id: int = Field(..., description="ID del usuario")
    location_id: int = Field(..., description="ID de la ubicación")
    role_in_location: Optional[str] = Field(None, description="Rol específico en esa ubicación")
    start_date: Optional[date] = Field(None, description="Fecha de inicio")
    notes: Optional[str] = Field(None, description="Notas adicionales")

# ==================== GESTIÓN DE UBICACIONES ====================

class LocationResponse(BaseModel):
    """Respuesta de ubicación"""
    id: int
    name: str
    type: str
    address: Optional[str]
    phone: Optional[str]
    is_active: bool
    created_at: datetime
    assigned_users_count: int
    total_products: int
    total_inventory_value: Decimal

class LocationStats(BaseModel):
    """Estadísticas de ubicación"""
    location_id: int
    location_name: str
    location_type: str
    daily_sales: Decimal
    monthly_sales: Decimal
    total_products: int
    low_stock_alerts: int
    pending_transfers: int
    active_users: int

# ==================== COSTOS OPERATIVOS ====================

class CostConfiguration(BaseModel):
    """Configuración de costos"""
    location_id: int = Field(..., description="Ubicación afectada")
    cost_type: CostType = Field(..., description="Tipo de costo")
    amount: Decimal = Field(..., gt=0, description="Monto del costo")
    frequency: str = Field(..., description="Frecuencia (monthly, weekly, daily)")
    description: str = Field(..., description="Descripción del costo")
    is_active: bool = Field(default=True, description="Si el costo está activo")
    effective_date: date = Field(..., description="Fecha de vigencia")

class CostResponse(BaseModel):
    """Respuesta de costo configurado"""
    id: int
    location_id: int
    location_name: str
    cost_type: str
    amount: Decimal
    frequency: str
    description: str
    is_active: bool
    effective_date: date
    created_by_user_id: int
    created_by_name: str
    created_at: datetime

# ==================== VENTAS AL POR MAYOR ====================

class WholesaleSaleCreate(BaseModel):
    """Crear venta al por mayor"""
    customer_name: str = Field(..., description="Nombre del cliente mayorista")
    customer_document: str = Field(..., description="Documento del cliente")
    customer_phone: Optional[str] = Field(None, description="Teléfono del cliente")
    location_id: int = Field(..., description="Ubicación donde se realiza la venta")
    items: List[Dict[str, Any]] = Field(..., description="Items de la venta")
    discount_percentage: Optional[Decimal] = Field(None, ge=0, le=100, description="Descuento aplicado")
    payment_method: str = Field(..., description="Método de pago")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class WholesaleSaleResponse(BaseModel):
    """Respuesta de venta al por mayor"""
    id: int
    customer_name: str
    customer_document: str
    customer_phone: Optional[str]
    location_id: int
    location_name: str
    total_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    payment_method: str
    sale_date: datetime
    processed_by_user_id: int
    processed_by_name: str
    items_count: int
    notes: Optional[str]

# ==================== REPORTES ====================

class SalesReport(BaseModel):
    """Reporte de ventas"""
    location_id: int
    location_name: str
    period_start: date
    period_end: date
    total_sales: Decimal
    total_transactions: int
    average_ticket: Decimal
    top_products: List[Dict[str, Any]]
    sales_by_day: List[Dict[str, Any]]
    sales_by_user: List[Dict[str, Any]]

class ReportFilter(BaseModel):
    """Filtros para reportes"""
    location_ids: Optional[List[int]] = Field(None, description="Ubicaciones específicas")
    start_date: date = Field(..., description="Fecha inicio")
    end_date: date = Field(..., description="Fecha fin")
    user_ids: Optional[List[int]] = Field(None, description="Usuarios específicos")
    product_categories: Optional[List[str]] = Field(None, description="Categorías de producto")
    sale_type: Optional[SaleType] = Field(None, description="Tipo de venta")

# ==================== ALERTAS DE INVENTARIO ====================

class InventoryAlert(BaseModel):
    """Configurar alerta de inventario"""
    location_id: int = Field(..., description="Ubicación a monitorear")
    alert_type: AlertType = Field(..., description="Tipo de alerta")
    threshold_value: int = Field(..., gt=0, description="Valor umbral")
    product_reference: Optional[str] = Field(None, description="Producto específico (opcional)")
    notification_emails: List[str] = Field(..., description="Emails para notificar")
    is_active: bool = Field(default=True, description="Si la alerta está activa")

class InventoryAlertResponse(BaseModel):
    """Respuesta de alerta configurada"""
    id: int
    location_id: int
    location_name: str
    alert_type: str
    threshold_value: int
    product_reference: Optional[str]
    notification_emails: List[str]
    is_active: bool
    created_by_user_id: int
    created_by_name: str
    created_at: datetime
    last_triggered: Optional[datetime]

# ==================== APROBACIÓN DE DESCUENTOS ====================

class DiscountApproval(BaseModel):
    """Aprobar/rechazar solicitud de descuento"""
    discount_request_id: int = Field(..., description="ID de la solicitud")
    approved: bool = Field(..., description="Si se aprueba o rechaza")
    admin_notes: Optional[str] = Field(None, description="Notas del administrador")
    max_discount_override: Optional[Decimal] = Field(None, description="Override del descuento máximo")

class DiscountRequestResponse(BaseModel):
    """Respuesta de solicitud de descuento"""
    id: int
    # sale_id: Optional[int] = None  # ← QUITAR si existe
    requester_user_id: int
    requester_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    original_amount: Decimal
    discount_amount: Decimal
    discount_percentage: Optional[Decimal] = None
    reason: str
    status: str
    requested_at: datetime
    approved_by_user_id: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    admin_notes: Optional[str] = None

# ==================== SUPERVISIÓN DE PERFORMANCE ====================

class UserPerformance(BaseModel):
    """Performance de usuario"""
    user_id: int
    user_name: str
    role: str
    location_id: int
    location_name: str
    period_start: date
    period_end: date
    metrics: Dict[str, Any]  # Métricas específicas por rol

class VendorPerformance(UserPerformance):
    """Performance específica de vendedor"""
    total_sales: Decimal
    total_transactions: int
    average_ticket: Decimal
    products_sold: int
    discounts_requested: int
    customer_satisfaction: Optional[float]

class WarehousePerformance(UserPerformance):
    """Performance específica de bodeguero"""
    transfers_processed: int
    average_processing_time: float
    returns_handled: int
    discrepancies_reported: int
    accuracy_rate: float

class CourierPerformance(UserPerformance):
    """Performance específica de corredor"""
    deliveries_completed: int
    average_delivery_time: float
    failed_deliveries: int
    incidents_reported: int
    on_time_rate: float

# ==================== ASIGNACIÓN DE MODELOS ====================

class ProductModelAssignment(BaseModel):
    """Asignar modelo a bodegas"""
    product_reference: str = Field(..., description="Código de referencia del producto")
    assigned_warehouses: List[int] = Field(..., description="IDs de bodegas asignadas")
    distribution_rules: Optional[Dict[str, Any]] = Field(None, description="Reglas de distribución")
    priority_warehouse_id: Optional[int] = Field(None, description="Bodega principal")
    min_stock_per_warehouse: Optional[int] = Field(None, description="Stock mínimo por bodega")
    max_stock_per_warehouse: Optional[int] = Field(None, description="Stock máximo por bodega")

class ProductModelAssignmentResponse(BaseModel):
    """Respuesta de asignación de modelo"""
    id: int
    product_reference: str
    product_brand: str
    product_model: str
    assigned_warehouses: List[Dict[str, Any]]
    distribution_rules: Optional[Dict[str, Any]]
    priority_warehouse_id: Optional[int]
    priority_warehouse_name: Optional[str]
    min_stock_per_warehouse: Optional[int]
    max_stock_per_warehouse: Optional[int]
    assigned_by_user_id: int
    assigned_by_name: str
    assigned_at: datetime

# ==================== DASHBOARD ADMINISTRATIVO ====================

class AdminDashboard(BaseModel):
    """Dashboard completo del administrador"""
    admin_name: str
    managed_locations: List[LocationStats]
    daily_summary: Dict[str, Any]
    pending_tasks: Dict[str, int]
    performance_overview: Dict[str, Any]
    alerts_summary: Dict[str, int]
    recent_activities: List[Dict[str, Any]]

class DashboardMetrics(BaseModel):
    """Métricas del dashboard"""
    total_sales_today: Decimal
    total_sales_month: Decimal
    active_users: int
    pending_transfers: int
    low_stock_alerts: int
    pending_discount_approvals: int
    avg_performance_score: float


class VideoProductEntry(BaseModel):
    """Entrada de producto mediante video IA"""
    video_file_path: str = Field(..., description="Ruta del archivo de video")
    warehouse_location_id: int = Field(..., description="ID de bodega destino")
    estimated_quantity: int = Field(..., gt=0, description="Cantidad estimada de productos")
    product_brand: Optional[str] = Field(None, description="Marca del producto (opcional)")
    product_model: Optional[str] = Field(None, description="Modelo del producto (opcional)")
    expected_sizes: Optional[List[str]] = Field(None, description="Tallas esperadas")
    notes: Optional[str] = Field(None, max_length=500, description="Notas adicionales")

class VideoProcessingResponse(BaseModel):
    """Respuesta del procesamiento de video"""
    id: int
    video_file_path: str
    warehouse_location_id: int
    warehouse_name: str
    estimated_quantity: int
    processing_status: str  # processing, completed, failed
    ai_extracted_info: Optional[Dict[str, Any]]
    detected_products: Optional[List[Dict[str, Any]]]
    confidence_score: Optional[float]
    processed_by_user_id: int
    processed_by_name: str
    processing_started_at: datetime
    processing_completed_at: Optional[datetime]
    error_message: Optional[str]
    notes: Optional[str]

class AIExtractionResult(BaseModel):
    """Resultado de extracción de IA"""
    detected_brand: Optional[str]
    detected_model: Optional[str]
    detected_colors: List[str]
    detected_sizes: List[str]
    confidence_scores: Dict[str, float]
    bounding_boxes: List[Dict[str, Any]]
    recommended_reference_code: Optional[str]


class AdminLocationAssignmentCreate(BaseModel):
    """Crear asignación de administrador a ubicación"""
    admin_id: int = Field(..., description="ID del administrador")
    location_id: int = Field(..., description="ID de la ubicación")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class AdminLocationAssignmentResponse(BaseModel):
    """Respuesta de asignación creada"""
    id: int
    admin_id: int
    admin_name: str
    location_id: int
    location_name: str
    location_type: str
    is_active: bool
    assigned_at: datetime
    assigned_by_name: Optional[str]
    notes: Optional[str]

class AdminLocationAssignmentBulk(BaseModel):
    """Asignación múltiple de administrador a ubicaciones"""
    admin_id: int = Field(..., description="ID del administrador")
    location_ids: List[int] = Field(..., description="IDs de las ubicaciones")
    notes: Optional[str] = Field(None, description="Notas para todas las asignaciones")


class CostConfigurationCreate(BaseModel):
    """Crear nueva configuración de costo"""
    location_id: int = Field(..., description="ID de la ubicación")
    cost_type: CostType = Field(..., description="Tipo de costo")
    amount: Decimal = Field(..., gt=0, description="Monto del costo")
    frequency: FrequencyType = Field(..., description="Frecuencia de cobro")
    description: str = Field(..., min_length=5, description="Descripción del costo")
    start_date: date = Field(..., description="Fecha de inicio")
    end_date: Optional[date] = Field(None, description="Fecha de finalización (opcional)")
    
    @validator('end_date')
    def validate_end_date(cls, v, values):
        if v and 'start_date' in values and v <= values['start_date']:
            raise ValueError('end_date debe ser posterior a start_date')
        return v

class CostConfigurationUpdate(BaseModel):
    """Actualizar configuración existente"""
    amount: Optional[Decimal] = Field(None, gt=0)
    frequency: Optional[FrequencyType] = None
    description: Optional[str] = Field(None, min_length=5)
    is_active: Optional[bool] = None
    end_date: Optional[date] = None

class CostConfigurationResponse(BaseModel):
    """Respuesta de configuración de costo"""
    id: int
    location_id: int
    location_name: str
    cost_type: str
    amount: Decimal
    frequency: str
    description: str
    is_active: bool
    start_date: date
    end_date: Optional[date]
    created_by_user_id: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ===== PAGOS =====

class CostPaymentCreate(BaseModel):
    """Registrar nuevo pago"""
    cost_configuration_id: int = Field(..., description="ID de la configuración de costo")
    due_date: date = Field(..., description="Fecha que se suponía vencer")
    payment_amount: Decimal = Field(..., gt=0, description="Monto pagado")
    payment_date: date = Field(..., description="Fecha real del pago")
    payment_method: str = Field(..., description="Método de pago")
    payment_reference: Optional[str] = Field(None, description="Referencia del pago")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class CostPaymentInstance(BaseModel):
    """Instancia de pago (calculada dinámicamente)"""
    cost_configuration_id: int
    due_date: date
    amount: Decimal
    status: PaymentStatus
    cost_type: str
    description: str
    frequency: str
    days_difference: Optional[int] = None  # Días hasta vencimiento o días vencido
    is_paid: bool = False
    payment_date: Optional[date] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None

class CostPaymentResponse(BaseModel):
    """Respuesta de pago registrado"""
    id: int
    cost_configuration_id: int
    due_date: date
    payment_date: date
    amount: Decimal
    payment_method: str
    payment_reference: Optional[str]
    notes: Optional[str]
    paid_by_user_id: int
    paid_by_name: str
    created_at: datetime

# ===== DASHBOARD =====

class CostDashboard(BaseModel):
    """Dashboard completo de costos"""
    location_id: int
    location_name: str
    total_monthly_costs: Decimal
    pending_payments: List[CostPaymentInstance]
    overdue_payments: List[CostPaymentInstance]
    upcoming_payments: List[CostPaymentInstance]
    paid_this_month: Decimal
    pending_this_month: Decimal
    overdue_amount: Decimal
    
    # Métricas adicionales
    total_configurations: int
    active_configurations: int
    next_payment_date: Optional[date]

class OperationalDashboard(BaseModel):
    """Dashboard operativo consolidado"""
    summary: Dict[str, Any]
    locations_status: List[Dict[str, Any]]
    critical_alerts: List[Dict[str, Any]]
    upcoming_week: List[Dict[str, Any]]
    monthly_summary: Dict[str, Decimal]

# ===== EXCEPCIONES =====

class CostPaymentExceptionCreate(BaseModel):
    """Crear excepción de pago"""
    cost_configuration_id: int
    exception_date: date
    exception_type: ExceptionType
    original_amount: Optional[Decimal] = None
    new_amount: Optional[Decimal] = None
    new_due_date: Optional[date] = None
    reason: str = Field(..., min_length=10)

# ===== ANÁLISIS =====

class DeletionAnalysis(BaseModel):
    """Análisis de impacto de eliminación"""
    has_payments: bool
    total_paid_payments: int
    total_paid_amount: Decimal
    has_exceptions: bool
    total_exceptions: int
    future_pending_count: int
    deletion_recommendation: str  # "safe_delete" o "deactivate"
    can_delete_safely: bool

class UpdateAmountRequest(BaseModel):
    """Solicitud de actualización de monto"""
    new_amount: Decimal = Field(..., gt=0)
    effective_date: date = Field(..., description="Fecha desde la cual aplica el nuevo monto")
    reason: Optional[str] = Field(None, description="Razón del cambio")
    
    @validator('effective_date')
    def validate_effective_date(cls, v):
        if v < date.today():
            raise ValueError('effective_date no puede ser en el pasado')
        return v

# ===== RESPUESTAS DE OPERACIONES =====

class CostOperationResponse(BaseModel):
    """Respuesta genérica de operaciones"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None

class PaymentRegistrationResponse(BaseModel):
    """Respuesta de registro de pago"""
    payment_id: int
    status: str
    next_due_date: Optional[date]
    message: str
    total_paid_amount: Decimal

# ==================== 🆕 SCHEMAS PARA TALLAS ESPECÍFICAS + IMAGEN ====================

class SizeQuantityEntry(BaseModel):
    """Entrada específica de cantidad por talla"""
    size: str = Field(..., min_length=1, max_length=10, description="Talla específica (ej: 39, 40, 41)")
    quantity: int = Field(..., gt=0, description="Cantidad exacta para esta talla")
    
    class Config:
        schema_extra = {
            "example": {
                "size": "40",
                "quantity": 5
            }
        }

class VideoProductEntryWithSizes(BaseModel):
    """Entrada de producto con tallas específicas e imagen de referencia"""
    warehouse_location_id: int = Field(..., description="ID de bodega destino")
    
    # 🆕 TALLAS CON CANTIDADES ESPECÍFICAS
    size_quantities: List[SizeQuantityEntry] = Field(
        ..., 
        min_items=1, 
        max_items=15,
        description="Cantidades específicas por talla"
    )
    
    # Información del producto
    product_brand: Optional[str] = Field(None, max_length=255, description="Marca del producto")
    product_model: Optional[str] = Field(None, max_length=255, description="Modelo del producto")
    notes: Optional[str] = Field(None, max_length=1000, description="Notas adicionales")
    unit_price: Decimal = Field(..., gt=0, description="Precio unitario del producto")
    box_price: Optional[Decimal] = Field(None, ge=0, description="Precio por caja (opcional)")
    
    @validator('size_quantities')
    def validate_sizes(cls, v):
        if not v:
            raise ValueError("Debe especificar al menos una talla")
        
        # Verificar que no haya tallas duplicadas
        sizes_seen = set()
        for sq in v:
            if sq.size in sizes_seen:
                raise ValueError(f"Talla duplicada: {sq.size}")
            sizes_seen.add(sq.size)
        
        total_quantity = sum([sq.quantity for sq in v])
        if total_quantity <= 0:
            raise ValueError("La cantidad total debe ser mayor a 0")
        if total_quantity > 1000:
            raise ValueError("La cantidad total no puede superar 1000 unidades")
            
        return v
    
    @property
    def total_quantity(self) -> int:
        """Calcular cantidad total automáticamente"""
        return sum([sq.quantity for sq in self.size_quantities])
    
    class Config:
        schema_extra = {
            "example": {
                "warehouse_location_id": 1,
                "size_quantities": [
                    {"size": "39", "quantity": 3},
                    {"size": "40", "quantity": 8},
                    {"size": "41", "quantity": 6},
                    {"size": "42", "quantity": 3}
                ],
                "product_brand": "Nike",
                "product_model": "Air Max 90",
                "notes": "Ingreso de inventario nuevo modelo"
            }
        }

class ProductCreationResponse(BaseModel):
    """Respuesta de creación de producto con imagen de referencia"""
    success: bool
    product_id: int
    reference_code: str
    
    # 🆕 IMAGEN DE REFERENCIA
    image_url: Optional[str] = Field(None, description="URL de imagen de referencia en Cloudinary")
    
    # Información del producto creado
    brand: str
    model: str
    total_quantity: int
    warehouse_name: str
    
    # Tallas creadas
    sizes_created: List[SizeQuantityEntry]
    unit_price: float = Field(..., description="Precio unitario del producto")
    box_price: Optional[float] = Field(None, description="Precio por caja del producto")
    
    
    # IA Results (si se procesó video)
    ai_confidence_score: Optional[float] = None
    ai_detected_info: Optional[Dict[str, Any]] = None
    
    # Metadatos
    created_by_user_id: int
    created_by_name: str
    created_at: datetime
    processing_time_seconds: Optional[float] = None

    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "product_id": 123,
                "reference_code": "NIKE-AIR90-ABC123",
                "image_url": "https://res.cloudinary.com/tustockya/image/upload/v1234567890/products/NIKE-AIR90-ABC_12345678.jpg",
                "brand": "Nike",
                "model": "Air Max 90",
                "total_quantity": 20,
                "warehouse_name": "Bodega Central",
                "unit_price": 250000.00,  
                "box_price": 1200000.00,  
                "sizes_created": [
                    {"size": "39", "quantity": 3},
                    {"size": "40", "quantity": 8}
                ],
                "ai_confidence_score": 0.95,
                "created_by_user_id": 1,
                "created_by_name": "Admin Usuario",
                "created_at": "2025-09-14T10:30:00",
                "processing_time_seconds": 45.2
            }
        }

# ==================== 🆕 SCHEMA PARA RESPUESTA DE ERROR ====================

class ProductCreationError(BaseModel):
    """Respuesta de error en creación de producto"""
    success: bool = False
    error_type: str  # "validation", "cloudinary", "ai_processing", "database"
    error_message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        schema_extra = {
            "example": {
                "success": False,
                "error_type": "cloudinary",
                "error_message": "Error subiendo imagen de referencia",
                "details": {"cloudinary_error": "Invalid image format"},
                "timestamp": "2025-09-14T10:30:00"
            }
        }