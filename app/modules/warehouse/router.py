# app/modules/warehouse/router.py
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, date

from app.config.database import get_db
from app.core.auth.dependencies import get_current_user, require_roles
from app.shared.database.models import User
from .service import WarehouseService
from .schemas import *

router = APIRouter(prefix="/warehouse", tags=["Warehouse - Bodeguero"])

# ==================== BG004: DEVOLUCIONES ====================

@router.post("/process-return", response_model=ReturnResponse)
async def process_product_return(
    return_data: ReturnCreate,
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG004: Recibir devoluciones de productos
    
    **Funcionalidad:**
    - Registrar devolución de productos desde locales
    - Validar condición del producto
    - Agregar al inventario si está en buen estado
    - Mantener trazabilidad completa
    
    **Casos de uso:**
    - Productos defectuosos devueltos por clientes
    - Exceso de inventario en locales
    - Productos de temporada no vendidos
    """
    service = WarehouseService(db)
    return await service.process_return(return_data, current_user)

@router.get("/my-returns", response_model=List[ReturnResponse])
async def get_my_processed_returns(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Obtener devoluciones procesadas por este bodeguero
    """
    service = WarehouseService(db)
    return service.repository.get_returns_by_warehouse(current_user.id, limit)

# ==================== BG005: UBICACIONES DE PRODUCTOS ====================

@router.post("/update-location", response_model=LocationUpdateResponse)
async def update_product_location(
    location_update: LocationUpdate,
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG005: Actualizar ubicaciones de productos entre bodegas/locales
    
    **Funcionalidad:**
    - Mover productos entre Bodega A, Bodega B, o Local X (exhibición)
    - Cambiar productos de bodega a exhibición en local
    - Redistribuir inventario entre ubicaciones
    - Procesar productos devueltos
    
    **Casos de uso:**
    - Traslados para exhibición: "Nike Air Max" de "Bodega Central" a "Local Norte - Exhibición"
    - Redistribución entre bodegas para balance de stock
    - Productos devueltos que van a diferentes ubicaciones
    
    **Resultado:** Sistema siempre refleja si producto está en bodega o en exhibición
    """
    service = WarehouseService(db)
    return await service.update_product_location(location_update, current_user)

# ==================== BG006: INVENTARIO POR UBICACIÓN ====================

@router.get("/inventory-by-location", response_model=List[InventoryByLocation])
async def get_inventory_by_location(
    location_ids: Optional[List[int]] = Query(None, description="IDs de ubicaciones específicas"),
    location_type: Optional[str] = Query(None, description="Tipo: bodega o local"),
    reference_code: Optional[str] = Query(None, description="Código de referencia"),
    brand: Optional[str] = Query(None, description="Marca específica"),
    min_stock: Optional[int] = Query(None, description="Stock mínimo"),
    max_stock: Optional[int] = Query(None, description="Stock máximo"),
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG006: Consultar inventario disponible por ubicación general
    
    **Propósito:** Ver qué productos hay en cada bodega o local específico
    
    **Funcionalidad:** 
    - Filtrar inventario por "Bodega Central", "Bodega Norte", "Local A - Exhibición"
    - Ver stock completo por ubicación con detalles de productos
    - Identificar rápidamente dónde buscar productos específicos
    
    **Casos de uso:**
    - Verificar stock de bodega antes de aceptar transferencia
    - Saber qué está en exhibición por local
    - Planificar redistribución de inventario
    
    **Resultado:** Bodeguero sabe en qué bodega buscar o si está exhibido en algún local
    """
    service = WarehouseService(db)
    
    filters = InventoryFilter(
        location_ids=location_ids,
        location_type=location_type,
        reference_code=reference_code,
        brand=brand,
        min_stock=min_stock,
        max_stock=max_stock
    )
    
    return await service.get_inventory_by_location(filters, current_user)

# ==================== BG007: HISTORIAL DE MOVIMIENTOS ====================

@router.get("/movement-history", response_model=List[MovementHistory])
async def get_movement_history(
    start_date: Optional[datetime] = Query(None, description="Fecha inicio"),
    end_date: Optional[datetime] = Query(None, description="Fecha fin"),
    movement_types: Optional[List[MovementType]] = Query(None, description="Tipos de movimiento"),
    location_ids: Optional[List[int]] = Query(None, description="Ubicaciones específicas"),
    reference_code: Optional[str] = Query(None, description="Código de referencia"),
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG007: Registrar historial de entregas y recepciones
    
    **Propósito:** Mantener trazabilidad completa de todos los movimientos del bodeguero
    
    **Funcionalidad:** Log automático de:
    - Qué entregó
    - A quién lo entregó  
    - Cuándo lo entregó
    - Qué recibió de vuelta
    
    **Casos de uso:**
    - Auditorías de inventario
    - Resolución de discrepancias
    - Evaluación de performance del bodeguero
    
    **Resultado:** Historial completo para responsabilidades y mejora de procesos
    """
    service = WarehouseService(db)
    
    filters = MovementHistoryFilter(
        start_date=start_date,
        end_date=end_date,
        movement_types=movement_types,
        location_ids=location_ids,
        reference_code=reference_code
    )
    
    return await service.get_movement_history(current_user, filters)

# ==================== BG008: MÚLTIPLES BODEGAS ====================

@router.get("/dashboard", response_model=WarehouseDashboard)
async def get_warehouse_dashboard(
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG008: Gestionar múltiples bodegas asignadas
    
    **Funcionalidad:**
    - Vista consolidada de todas las bodegas asignadas
    - Métricas de performance por bodega
    - Tareas pendientes en cada ubicación
    - Estadísticas del día consolidadas
    
    **Dashboard incluye:**
    - Lista de bodegas asignadas con estado
    - Solicitudes pendientes por bodega
    - Movimientos del día
    - Actividades recientes
    """
    service = WarehouseService(db)
    return await service.get_warehouse_dashboard(current_user)

@router.get("/assigned-warehouses", response_model=List[AssignedWarehouse])
async def get_assigned_warehouses(
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Obtener lista de bodegas asignadas al bodeguero
    """
    service = WarehouseService(db)
    warehouses = service.repository.get_assigned_warehouses(current_user.id)
    
    return [
        AssignedWarehouse(
            location_id=w.id,
            location_name=w.name,
            location_type=w.type,
            address=w.address,
            phone=w.phone,
            is_active=w.is_active,
            total_products=0,  # Se calcularía con query adicional
            total_units=0,
            pending_requests=0,
            last_activity=None
        ) for w in warehouses
    ]

# ==================== BG009: DISCREPANCIAS ====================

@router.post("/report-discrepancy", response_model=DiscrepancyResponse)
async def report_inventory_discrepancy(
    discrepancy: DiscrepancyReport,
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG009: Reportar discrepancias de inventario
    
    **Funcionalidad:**
    - Reportar diferencias entre inventario físico y sistema
    - Clasificar tipo de discrepancia (faltante, sobrante, dañado, etc.)
    - Adjuntar fotos como evidencia
    - Establecer prioridad según impacto
    
    **Tipos de discrepancias:**
    - MISSING: Falta producto que debería estar
    - EXCESS: Sobra producto no registrado
    - DAMAGED: Producto dañado no reportado
    - LOCATION_ERROR: Producto en ubicación incorrecta
    - SIZE_ERROR: Talla incorrecta registrada
    
    **Proceso:**
    1. Bodeguero encuentra discrepancia durante conteo físico
    2. Documenta diferencia con fotos de evidencia
    3. Sistema genera reporte para administrador
    4. Se programa corrección del inventario
    """
    service = WarehouseService(db)
    return await service.report_inventory_discrepancy(discrepancy, current_user)

# ==================== BG010: REVERSIÓN DE MOVIMIENTOS ====================

@router.post("/reverse-movement", response_model=MovementReversalResponse)
async def reverse_inventory_movement(
    reversal: MovementReversal,
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG010: Revertir movimientos de inventario en caso de entrega fallida
    
    **Funcionalidad:**
    - Restaurar stock si corredor no puede completar entrega
    - Revertir movimientos por errores de procesamiento
    - Mantener trazabilidad de reversiones
    - Actualizar inventario automáticamente
    
    **Casos de uso:**
    - Corredor reporta entrega fallida
    - Error en procesamiento de transferencia
    - Cliente cancela pedido después de entrega iniciada
    - Producto dañado durante transporte
    
    **Proceso:**
    1. Identificar movimiento original a revertir
    2. Calcular cantidades a restaurar
    3. Actualizar stock en ubicación original
    4. Registrar reversión con razón detallada
    """
    service = WarehouseService(db)
    return await service.reverse_inventory_movement(reversal, current_user)

# ==================== BG010: INGRESO CON VIDEO ====================

@router.post("/video-product-entry", response_model=VideoProcessingResponse)
async def process_video_product_entry(
    warehouse_location_id: int,
    estimated_quantity: int,
    notes: Optional[str] = None,
    video_file: UploadFile = File(..., description="Video mostrando el producto"),
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    BG010: Ingreso de nueva mercancía mediante video para entrenamiento de IA
    
    **Funcionalidad:**
    - Subir video mostrando el producto de referencia
    - Registrar información completa: modelo, referencia, precio, tallas disponibles
    - Especificar cantidad por caja y por unidad
    - Asignar bodega(s) de almacenamiento del modelo
    - Sistema procesa video automáticamente para entrenar IA
    
    **Proceso:**
    1. Bodeguero graba video del producto nuevo
    2. Especifica bodega de almacenamiento y cantidad estimada
    3. Sistema procesa video con IA para extraer características
    4. IA identifica: marca, modelo, color, tallas visibles
    5. Sistema crea registro para posterior verificación
    6. Video se usa para mejorar precisión del escaneo IA
    
    **Requisitos del video:**
    - Mostrar producto desde múltiples ángulos
    - Incluir etiquetas y tallas visibles
    - Buena iluminación y enfoque
    - Duración recomendada: 30-60 segundos
    """
    service = WarehouseService(db)
    
    # Validar archivo de video
    if not video_file.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail="Archivo debe ser un video")
    
    video_entry = VideoProductEntry(
        video_file_path="",  # Se establecerá en el servicio
        warehouse_location_id=warehouse_location_id,
        estimated_quantity=estimated_quantity,
        notes=notes
    )
    
    return await service.process_video_product_entry(video_entry, video_file, current_user)

@router.get("/video-entries", response_model=List[VideoProcessingResponse])
async def get_video_processing_history(
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Estado: processing, completed, failed"),
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Obtener historial de videos procesados para entrenamiento de IA
    """
    # Esta funcionalidad se implementaría con una tabla específica para videos
    # Por ahora retornamos un ejemplo
    return []

# ==================== ENDPOINTS DE UTILIDAD ====================

@router.get("/health")
async def warehouse_module_health():
    """
    Verificar estado del módulo warehouse
    """
    return {
        "module": "warehouse",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "BG001 - Procesar solicitudes ✅ (en módulo transfers)",
            "BG002 - Confirmar disponibilidad ✅ (en módulo transfers)", 
            "BG003 - Entregar a corredor ✅ (en módulo transfers)",
            "BG004 - Recibir devoluciones ✅",
            "BG005 - Actualizar ubicaciones ✅",
            "BG006 - Inventario por ubicación ✅",
            "BG007 - Historial de movimientos ✅",
            "BG008 - Múltiples bodegas ✅",
            "BG009 - Reportar discrepancias ✅",
            "BG010 - Reversión de movimientos ✅",
            "BG010 - Ingreso con video ✅"
        ]
    }

@router.get("/statistics")
async def get_warehouse_statistics(
    current_user: User = Depends(require_roles(["bodeguero", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Estadísticas generales del módulo warehouse
    """
    service = WarehouseService(db)
    
    # Estadísticas básicas
    today = date.today()
    
    stats = {
        "today": {
            "transfers_processed": 0,  # Se calcularía con query
            "returns_processed": 0,   # Se calcularía con query
            "location_updates": 0,    # Se calcularía con query
            "discrepancies_reported": 0  # Se calcularía con query
        },
        "assigned_warehouses_count": len(service.repository.get_assigned_warehouses(current_user.id)),
        "total_inventory_movements": 0,  # Se calcularía con query
        "active_discrepancies": 0  # Se calcularía con query
    }
    
    return stats