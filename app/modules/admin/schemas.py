# app/modules/admin/schemas.py
from pydantic import BaseModel, Field, EmailStr, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class UserRole(str, Enum):
    """Roles de usuario que puede crear el administrador"""
    VENDEDOR = "vendedor"
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
    sale_id: int
    requester_user_id: int
    requester_name: str
    location_id: int
    location_name: str
    original_amount: Decimal
    discount_amount: Decimal
    discount_percentage: Decimal
    reason: str
    status: str
    requested_at: datetime
    approved_by_user_id: Optional[int]
    approved_by_name: Optional[str]
    approved_at: Optional[datetime]
    admin_notes: Optional[str]

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