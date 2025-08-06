# app/modules/warehouse/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum

class DiscrepancyType(str, Enum):
    """Tipos de discrepancias de inventario"""
    MISSING = "missing"           # Falta producto
    EXCESS = "excess"            # Sobra producto  
    DAMAGED = "damaged"          # Producto dañado
    LOCATION_ERROR = "location_error"  # Ubicación incorrecta
    SIZE_ERROR = "size_error"    # Talla incorrecta

class MovementType(str, Enum):
    """Tipos de movimientos de inventario"""
    TRANSFER_IN = "transfer_in"      # Entrada por transferencia
    TRANSFER_OUT = "transfer_out"    # Salida por transferencia
    RETURN = "return"               # Devolución
    ADJUSTMENT = "adjustment"       # Ajuste de inventario
    DAMAGE = "damage"              # Producto dañado
    LOST = "lost"                  # Producto perdido

class LocationUpdateType(str, Enum):
    """Tipos de actualización de ubicación"""
    BODEGA_TO_BODEGA = "bodega_to_bodega"      # Entre bodegas
    BODEGA_TO_EXHIBITION = "bodega_to_exhibition"  # A exhibición
    EXHIBITION_TO_BODEGA = "exhibition_to_bodega"  # De exhibición a bodega
    EXHIBITION_TO_EXHIBITION = "exhibition_to_exhibition"  # Entre exhibiciones

# ==================== DEVOLUCIONES ====================

class ReturnCreate(BaseModel):
    """Crear devolución de producto"""
    sneaker_reference_code: str = Field(..., description="Código de referencia del producto")
    size: str = Field(..., description="Talla del producto")
    quantity: int = Field(..., gt=0, description="Cantidad a devolver")
    reason: str = Field(..., description="Razón de la devolución")
    condition: str = Field(..., description="Condición del producto (nuevo, usado, dañado)")
    origin_location_id: int = Field(..., description="Ubicación de origen")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class ReturnResponse(BaseModel):
    """Respuesta de devolución procesada"""
    id: int
    sneaker_reference_code: str
    size: str
    quantity: int
    reason: str
    condition: str
    origin_location_id: int
    origin_location_name: str
    received_by_user_id: int
    received_by_name: str
    received_at: datetime
    notes: Optional[str]
    status: str

# ==================== UBICACIONES DE PRODUCTOS ====================

class LocationUpdate(BaseModel):
    """Actualizar ubicación de producto"""
    sneaker_reference_code: str = Field(..., description="Código de referencia")
    size: str = Field(..., description="Talla")
    quantity: int = Field(..., gt=0, description="Cantidad a mover")
    source_location_id: int = Field(..., description="Ubicación origen")
    destination_location_id: int = Field(..., description="Ubicación destino")
    movement_type: LocationUpdateType = Field(..., description="Tipo de movimiento")
    reason: str = Field(..., description="Razón del movimiento")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class LocationUpdateResponse(BaseModel):
    """Respuesta de actualización de ubicación"""
    id: int
    sneaker_reference_code: str
    size: str
    quantity: int
    source_location_id: int
    source_location_name: str
    destination_location_id: int
    destination_location_name: str
    movement_type: str
    reason: str
    moved_by_user_id: int
    moved_by_name: str
    moved_at: datetime
    notes: Optional[str]

# ==================== INVENTARIO POR UBICACIÓN ====================

class InventoryByLocation(BaseModel):
    """Inventario agrupado por ubicación"""
    location_id: int
    location_name: str
    location_type: str
    total_products: int
    total_units: int
    products: List[Dict[str, Any]]

class InventoryFilter(BaseModel):
    """Filtros para consulta de inventario"""
    location_ids: Optional[List[int]] = Field(None, description="IDs de ubicaciones específicas")
    location_type: Optional[str] = Field(None, description="Tipo de ubicación (bodega/local)")
    reference_code: Optional[str] = Field(None, description="Código de referencia específico")
    brand: Optional[str] = Field(None, description="Marca específica")
    min_stock: Optional[int] = Field(None, description="Stock mínimo")
    max_stock: Optional[int] = Field(None, description="Stock máximo")

# ==================== HISTORIAL DE MOVIMIENTOS ====================

class MovementHistory(BaseModel):
    """Historial de movimientos del bodeguero"""
    id: int
    movement_type: str
    sneaker_reference_code: str
    brand: str
    model: str
    size: str
    quantity: int
    source_location_id: Optional[int]
    source_location_name: Optional[str]
    destination_location_id: Optional[int]
    destination_location_name: Optional[str]
    handled_by_user_id: int
    handled_by_name: str
    handled_at: datetime
    notes: Optional[str]
    related_transfer_id: Optional[int]

class MovementHistoryFilter(BaseModel):
    """Filtros para historial de movimientos"""
    start_date: Optional[datetime] = Field(None, description="Fecha inicio")
    end_date: Optional[datetime] = Field(None, description="Fecha fin")
    movement_types: Optional[List[MovementType]] = Field(None, description="Tipos de movimiento")
    location_ids: Optional[List[int]] = Field(None, description="Ubicaciones específicas")
    reference_code: Optional[str] = Field(None, description="Código de referencia")

# ==================== DISCREPANCIAS DE INVENTARIO ====================

class DiscrepancyReport(BaseModel):
    """Reporte de discrepancia de inventario"""
    location_id: int = Field(..., description="Ubicación donde se encontró la discrepancia")
    sneaker_reference_code: str = Field(..., description="Código de referencia")
    size: str = Field(..., description="Talla")
    discrepancy_type: DiscrepancyType = Field(..., description="Tipo de discrepancia")
    expected_quantity: int = Field(..., description="Cantidad esperada en sistema")
    actual_quantity: int = Field(..., description="Cantidad real encontrada")
    difference: int = Field(..., description="Diferencia (actual - esperado)")
    description: str = Field(..., description="Descripción detallada")
    photos: Optional[List[str]] = Field(None, description="URLs de fotos de evidencia")
    priority: str = Field(default="medium", description="Prioridad (low/medium/high)")

class DiscrepancyResponse(BaseModel):
    """Respuesta de discrepancia reportada"""
    id: int
    location_id: int
    location_name: str
    sneaker_reference_code: str
    brand: str
    model: str
    size: str
    discrepancy_type: str
    expected_quantity: int
    actual_quantity: int
    difference: int
    description: str
    photos: Optional[List[str]]
    priority: str
    reported_by_user_id: int
    reported_by_name: str
    reported_at: datetime
    status: str
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]

# ==================== GESTIÓN DE MÚLTIPLES BODEGAS ====================

class AssignedWarehouse(BaseModel):
    """Bodega asignada al bodeguero"""
    location_id: int
    location_name: str
    location_type: str
    address: Optional[str]
    phone: Optional[str]
    is_active: bool
    total_products: int
    total_units: int
    pending_requests: int
    last_activity: Optional[datetime]

class WarehouseDashboard(BaseModel):
    """Dashboard del bodeguero"""
    user_name: str
    assigned_warehouses: List[AssignedWarehouse]
    daily_stats: Dict[str, Any]
    pending_tasks: Dict[str, int]
    recent_activities: List[MovementHistory]

# ==================== INGRESO DE MERCANCÍA CON VIDEO ====================

class VideoProductEntry(BaseModel):
    """Ingreso de producto mediante video"""
    video_file_path: str = Field(..., description="Ruta del archivo de video")
    warehouse_location_id: int = Field(..., description="Bodega donde se almacenará")
    estimated_quantity: int = Field(..., gt=0, description="Cantidad estimada total")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class VideoProcessingResponse(BaseModel):
    """Respuesta del procesamiento de video"""
    id: int
    video_file_path: str
    warehouse_location_id: int
    warehouse_name: str
    estimated_quantity: int
    processing_status: str  # processing, completed, failed
    ai_results: Optional[Dict[str, Any]]
    processed_by_user_id: int
    processed_by_name: str
    processed_at: datetime
    notes: Optional[str]

# ==================== REVERSIÓN DE MOVIMIENTOS ====================

class MovementReversal(BaseModel):
    """Reversión de movimiento de inventario"""
    original_movement_id: int = Field(..., description="ID del movimiento original")
    reason: str = Field(..., description="Razón de la reversión")
    notes: Optional[str] = Field(None, description="Notas adicionales")

class MovementReversalResponse(BaseModel):
    """Respuesta de reversión de movimiento"""
    id: int
    original_movement_id: int
    reversal_type: str
    sneaker_reference_code: str
    size: str
    quantity: int
    location_affected_id: int
    location_affected_name: str
    reason: str
    reversed_by_user_id: int
    reversed_by_name: str
    reversed_at: datetime
    notes: Optional[str]
