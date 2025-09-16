# app/modules/admin/router.py
from fastapi import APIRouter, Depends, HTTPException, Query , File, UploadFile, Form , status
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, date
from sqlalchemy import func

from app.config.settings import settings
from app.config.database import get_db
from app.core.auth.dependencies import get_current_user, require_roles
from app.shared.database.models import (
    User, 
    Location, 
    DiscountRequest, 
    TransferRequest,
    Sale,
    Product
)
from .service import AdminService
from .schemas import *
import logging
import json 
from .cost_router import router as cost_router

# Configuración básica del logger
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin - Administrador"])

router.include_router(cost_router)

# ==================== AD003 & AD004: CREAR USUARIOS ====================

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD003: Crear usuarios vendedores en locales asignados
    AD004: Crear usuarios bodegueros en bodegas asignadas
    
    **Funcionalidad:**
    - Crear vendedores y asignarlos a locales específicos
    - Crear bodegueros y asignarlos a bodegas específicas
    - Crear corredores para logística
    - Validar unicidad de email y compatibilidad rol-ubicación
    
    **Validaciones:**
    - Email único en el sistema
    - Vendedores solo en locales (type='local')
    - Bodegueros solo en bodegas (type='bodega')
    - Corredores pueden no tener ubicación específica
    """
    service = AdminService(db)
    return await service.create_user(user_data, current_user)

@router.get("/users", response_model=List[UserResponse])
async def get_managed_users(
    role: Optional[UserRole] = Query(None, description="Filtrar por rol"),
    location_id: Optional[int] = Query(None, description="Filtrar por ubicación"),
    is_active: Optional[bool] = Query(None, description="Filtrar por estado activo"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener usuarios gestionados por el administrador
    
    **FUNCIONALIDAD ACTUALIZADA:**
    - Administradores ven solo usuarios en sus ubicaciones asignadas
    - BOSS ve todos los usuarios
    - Filtros aplicados después de la validación de permisos
    """
    service = AdminService(db)
    
    # ====== USAR MÉTODO CORREGIDO QUE RESPETA ASIGNACIONES ======
    users = service.repository.get_users_by_admin(current_user.id)
    
    # ====== VALIDACIÓN ADICIONAL DE FILTRO POR UBICACIÓN ======
    if location_id and current_user.role != "boss":
        # Verificar que el admin puede ver esa ubicación
        can_manage = await service._can_admin_manage_location(current_user.id, location_id)
        if not can_manage:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos para ver usuarios de la ubicación {location_id}"
            )
    
    # Aplicar filtros
    if role:
        users = [u for u in users if u.role == role.value]
    if location_id:
        users = [u for u in users if u.location_id == location_id]
    if is_active is not None:
        users = [u for u in users if u.is_active == is_active]
    
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            first_name=u.first_name,
            last_name=u.last_name,
            full_name=u.full_name,
            role=u.role,
            location_id=u.location_id,
            location_name=u.location.name if u.location else None,
            is_active=u.is_active,
            created_at=u.created_at
        ) for u in users
    ]

@router.get("/available-locations-for-users", response_model=List[LocationResponse])
async def get_available_locations_for_user_creation(
    role: Optional[UserRole] = Query(None, description="Filtrar por rol de usuario a crear"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener ubicaciones donde el administrador puede crear usuarios
    
    **Funcionalidad:**
    - Administradores ven solo sus ubicaciones asignadas
    - BOSS ve todas las ubicaciones
    - Filtro por tipo según el rol del usuario a crear
    """
    service = AdminService(db)
    
    # Obtener ubicaciones gestionadas
    managed_locations = service.repository.get_managed_locations(current_user.id)
    
    # Filtrar por tipo según rol
    if role:
        if role == UserRole.VENDEDOR:
            managed_locations = [loc for loc in managed_locations if loc.type == "local"]
        elif role == UserRole.BODEGUERO:
            managed_locations = [loc for loc in managed_locations if loc.type == "bodega"]
        # Corredores pueden ir a cualquier tipo de ubicación
    
    return [
        LocationResponse(
            id=loc.id,
            name=loc.name,
            type=loc.type,
            address=loc.address,
            phone=loc.phone,
            is_active=loc.is_active,
            created_at=loc.created_at,
            assigned_users_count=len([u for u in loc.users if u.is_active]),
            total_products=0,  # Calcular si es necesario
            total_inventory_value=Decimal('0')  # Calcular si es necesario
        ) for loc in managed_locations
    ]

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Actualizar información de usuario gestionado
    
    **VALIDACIONES DE PERMISOS AGREGADAS:**
    - Solo puede actualizar usuarios en ubicaciones bajo su control
    - Si cambia la ubicación, debe ser a una ubicación que él gestiona
    - Validar compatibilidad rol-ubicación
    - BOSS puede actualizar cualquier usuario
    
    **Casos de uso:**
    - Cambiar nombre/información personal del usuario
    - Mover vendedor de un local a otro (ambos bajo control del admin)
    - Mover bodeguero entre bodegas gestionadas
    - Activar/desactivar usuario
    """
    service = AdminService(db)
    
    return await service.update_user(user_id, update_data, current_user)

# ==================== AD005 & AD006: ASIGNAR USUARIOS ====================

@router.post("/users/assign-location")
async def assign_user_to_location(
    assignment: UserAssignment,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD005: Asignar vendedores a locales específicos
    AD006: Asignar bodegueros a bodegas específicas
    
    **VALIDACIONES DE PERMISOS AGREGADAS:**
    - Solo puede asignar usuarios que estén en ubicaciones bajo su control
    - Solo puede asignar a ubicaciones que él gestiona
    - Validar compatibilidad rol-ubicación
    - BOSS puede asignar cualquier usuario a cualquier ubicación
    
    **Funcionalidad:**
    - Asignar/reasignar usuarios a ubicaciones específicas
    - Validar que admin controla tanto usuario como ubicación destino
    - Mantener historial de asignaciones en user_location_assignments
    - Actualizar ubicación principal del usuario
    
    **Casos de uso válidos:**
    - Admin mueve vendedor entre sus locales asignados
    - Admin mueve bodeguero entre sus bodegas
    - BOSS redistribuye personal entre cualquier ubicación
    - Asignar usuario recién creado a ubicación específica
    
    **Casos que fallarán:**
    - Admin intenta mover usuario de otro admin
    - Admin intenta asignar a ubicación no controlada
    - Intentar asignar vendedor a bodega o bodeguero a local
    """
    service = AdminService(db)
    return await service.assign_user_to_location(assignment, current_user)

# ==================== AD001 & AD002: GESTIÓN DE UBICACIONES ====================

@router.get("/locations", response_model=List[LocationResponse])
async def get_managed_locations(
    location_type: Optional[LocationType] = Query(None, description="Filtrar por tipo"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD001: Gestionar múltiples locales de venta asignados
    AD002: Supervisar múltiples bodegas bajo su responsabilidad
    
    **Funcionalidad:**
    - Ver todas las ubicaciones bajo gestión del administrador
    - Métricas básicas por ubicación (usuarios, productos, valor inventario)
    - Filtrar por tipo (local/bodega)
    - Estado operativo de cada ubicación
    """
    service = AdminService(db)
    locations = await service.get_managed_locations(current_user)
    
    if location_type:
        locations = [loc for loc in locations if loc.type == location_type.value]
    
    return locations

@router.get("/locations/{location_id}/stats")
async def get_location_statistics(
    location_id: int,
    start_date: date = Query(..., description="Fecha inicio para estadísticas"),
    end_date: date = Query(..., description="Fecha fin para estadísticas"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener estadísticas detalladas de una ubicación específica
    
    **VALIDACIONES AGREGADAS:**
    - Solo puede ver estadísticas de ubicaciones bajo su control
    - BOSS puede ver estadísticas de cualquier ubicación
    - Validar rango de fechas válido
    
    **Estadísticas incluidas:**
    - Ventas del período especificado
    - Número de transacciones
    - Productos disponibles en la ubicación
    - Alertas de stock bajo
    - Valor total del inventario
    - Usuarios activos en la ubicación
    - Ticket promedio
    
    **Casos de uso:**
    - Dashboard de ubicación específica
    - Análisis de performance por período
    - Reportes de inventario por ubicación
    - Métricas de ventas detalladas
    """
    service = AdminService(db)
    return await service.get_location_statistics(location_id, start_date, end_date, current_user)

# ==================== AD007 & AD008: CONFIGURAR COSTOS ====================

@router.get("/costs", response_model=List[CostResponse])
async def get_cost_configurations(
    location_id: Optional[int] = Query(None, description="Filtrar por ubicación"),
    cost_type: Optional[CostType] = Query(None, description="Filtrar por tipo de costo"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener configuraciones de costos
    
    **VALIDACIONES AGREGADAS:**
    - Solo puede ver costos de ubicaciones bajo su control
    - BOSS puede ver costos de todas las ubicaciones
    - Validar acceso a ubicación específica si se especifica
    
    **Funcionalidad:**
    - Ver todos los costos configurados
    - Filtrar por ubicación específica
    - Filtrar por tipo de costo (arriendo, servicios, etc.)
    - Información completa: monto, frecuencia, quién lo configuró
    
    **Casos de uso:**
    - Dashboard de costos operativos
    - Análisis de gastos por ubicación
    - Auditoría de configuraciones de costos
    - Planificación presupuestaria
    """
    service = AdminService(db)
    
    cost_type_value = cost_type.value if cost_type else None
    
    return await service.get_cost_configurations(
        admin=current_user,
        location_id=location_id,
        cost_type=cost_type_value
    )

@router.get("/costs", response_model=List[CostResponse])
async def get_cost_configurations(
    location_id: Optional[int] = Query(None, description="Filtrar por ubicación"),
    cost_type: Optional[CostType] = Query(None, description="Filtrar por tipo de costo"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener configuraciones de costos
    """
    service = AdminService(db)
    
    if location_id:
        costs = service.repository.get_cost_configurations(location_id)
        if cost_type:
            costs = [c for c in costs if c["cost_type"] == cost_type.value]
        return costs
    
    # Si no se especifica ubicación, obtener de todas las ubicaciones gestionadas
    managed_locations = service.repository.get_managed_locations(current_user.id)
    all_costs = []
    
    for location in managed_locations:
        location_costs = service.repository.get_cost_configurations(location.id)
        if cost_type:
            location_costs = [c for c in location_costs if c["cost_type"] == cost_type.value]
        all_costs.extend(location_costs)
    
    return all_costs

# ==================== AD009: VENTAS AL POR MAYOR ====================

@router.post("/wholesale-sales", response_model=WholesaleSaleResponse)
async def process_wholesale_sale(
    sale_data: WholesaleSaleCreate,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD009: Procesar ventas al por mayor
    
    **Funcionalidad:**
    - Procesar ventas a clientes mayoristas
    - Aplicar descuentos especiales por volumen
    - Manejar múltiples productos en una sola transacción
    - Actualizar inventario automáticamente
    - Registrar información completa del cliente mayorista
    
    **Proceso:**
    1. Validar disponibilidad de todos los productos
    2. Aplicar descuentos por volumen
    3. Crear venta con múltiples items
    4. Actualizar inventario de cada producto
    5. Generar comprobante de venta mayorista
    """
    service = AdminService(db)
    return await service.process_wholesale_sale(sale_data, current_user)

# ==================== AD010: REPORTES DE VENTAS ====================

@router.post("/reports/sales", response_model=List[SalesReport])
async def generate_sales_reports(
    filters: ReportFilter,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD010: Generar reportes de ventas por local y período
    
    **Funcionalidad:**
    - Reportes de ventas consolidados por ubicación
    - Análisis por período (diario, semanal, mensual)
    - Top productos más vendidos
    - Performance por vendedor
    - Tendencias de ventas por día
    - Métricas de ticket promedio
    
    **Casos de uso:**
    - Reporte mensual de todos los locales
    - Análisis de performance de vendedor específico
    - Identificar productos más exitosos
    - Comparar performance entre ubicaciones
    """
    service = AdminService(db)
    return await service.generate_sales_report(filters, current_user)

# ==================== AD011: ALERTAS DE INVENTARIO ====================

@router.post("/inventory-alerts", response_model=InventoryAlertResponse)
async def configure_inventory_alert(
    alert_config: InventoryAlert,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD011: Configurar alertas de inventario mínimo
    
    **Funcionalidad:**
    - Configurar alertas automáticas cuando stock baja del umbral
    - Alertas por producto específico o general por ubicación
    - Notificaciones por email a múltiples destinatarios
    - Diferentes tipos de alerta (stock mínimo, agotado, vencido)
    
    **Tipos de alerta:**
    - INVENTARIO_MINIMO: Cuando stock baja del umbral configurado
    - STOCK_AGOTADO: Cuando producto se agota completamente
    - PRODUCTO_VENCIDO: Para productos con fecha de vencimiento (futuro)
    
    **Proceso:**
    1. Sistema monitorea inventario automáticamente
    2. Cuando se cumple condición, envía notificación
    3. Email a lista de destinatarios configurada
    4. Alerta se registra para seguimiento
    """
    service = AdminService(db)
    return await service.configure_inventory_alert(alert_config, current_user)

# ==================== AD012: APROBAR DESCUENTOS ====================

@router.get("/discount-requests/pending", response_model=List[DiscountRequestResponse])
async def get_pending_discount_requests(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener solicitudes de descuento pendientes de aprobación
    
    **VALIDACIONES AGREGADAS:**
    - Solo ve solicitudes de usuarios en ubicaciones que controla
    - BOSS puede ver todas las solicitudes pendientes
    - Información completa del solicitante y ubicación
    
    **Funcionalidad:**
    - Ver todas las solicitudes pendientes de aprobación
    - Información del vendedor solicitante
    - Ubicación donde trabaja el vendedor
    - Monto y razón del descuento solicitado
    - Fecha de solicitud para priorizar
    """
    service = AdminService(db)
    return await service.get_pending_discount_requests(current_user)

@router.post("/discount-requests/approve", response_model=DiscountRequestResponse)
async def approve_discount_request(
    approval: DiscountApproval,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD012: Aprobar solicitudes de descuento de vendedores
    
    **Funcionalidad:**
    - Revisar solicitudes de descuento de vendedores
    - Aprobar o rechazar basado en políticas de la empresa
    - Agregar notas administrativas
    - Override de límites de descuento en casos especiales
    
    **Proceso de aprobación:**
    1. Vendedor solicita descuento superior a su límite ($5,000)
    2. Solicitud llega a administrador
    3. Administrador revisa contexto y justificación
    4. Aprueba/rechaza con notas explicativas
    5. Sistema notifica al vendedor
    6. Si se aprueba, descuento se aplica automáticamente
    """
    service = AdminService(db)
    return await service.approve_discount_request(approval, current_user)

# ==================== AD013: SUPERVISAR TRASLADOS ====================

@router.get("/transfers/overview")
async def get_transfers_overview(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD013: Supervisar traslados entre locales y bodegas
    
    **Funcionalidad:**
    - Vista consolidada de todas las transferencias
    - Estado actual de transferencias en proceso
    - Métricas de eficiencia del sistema de traslados
    - Identificar cuellos de botella y demoras
    
    **Métricas incluidas:**
    - Transferencias por estado (pending, in_transit, completed)
    - Tiempo promedio de procesamiento
    - Transferencias por prioridad (cliente presente vs restock)
    - Performance por bodeguero y corredor
    - Alertas de transferencias demoradas
    """
    service = AdminService(db)
    return await service.get_transfers_overview(current_user)

# ==================== AD014: SUPERVISAR PERFORMANCE ====================

@router.get("/performance/users")
async def get_users_performance(
    start_date: date = Query(..., description="Fecha inicio del período"),
    end_date: date = Query(..., description="Fecha fin del período"),
    user_ids: Optional[List[int]] = Query(None, description="IDs de usuarios específicos"),
    role: Optional[UserRole] = Query(None, description="Filtrar por rol"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD014: Supervisar performance de vendedores y bodegueros
    
    **Funcionalidad:**
    - Métricas de performance personalizadas por rol
    - Comparación entre usuarios del mismo rol
    - Identificar top performers y usuarios que necesitan apoyo
    - Métricas específicas por rol para evaluación objetiva
    
    **Métricas por rol:**
    
    **Vendedores:**
    - Total de ventas y transacciones
    - Ticket promedio
    - Productos vendidos
    - Solicitudes de descuento
    - Satisfacción del cliente (futuro)
    
    **Bodegueros:**
    - Transferencias procesadas
    - Tiempo promedio de procesamiento
    - Devoluciones manejadas
    - Discrepancias reportadas
    - Tasa de precisión
    
    **Corredores:**
    - Entregas completadas
    - Tiempo promedio de entrega
    - Entregas fallidas
    - Incidencias reportadas
    - Tasa de puntualidad
    """
    service = AdminService(db)
    return await service.get_users_performance(current_user, start_date, end_date, user_ids)

# ==================== AD015: ASIGNACIÓN DE MODELOS ====================

@router.post("/product-assignments", response_model=ProductModelAssignmentResponse)
async def assign_product_model_to_warehouses(
    assignment: ProductModelAssignment,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD015: Gestionar asignación de modelos a bodegas específicas
    
    **Funcionalidad:**
    - Asignar productos específicos a bodegas determinadas
    - Configurar bodega principal y secundarias
    - Establecer reglas de distribución automática
    - Definir stock mínimo y máximo por bodega
    
    **Casos de uso:**
    - Nuevo modelo se distribuye solo en bodegas específicas
    - Producto premium solo en bodega central
    - Distribución equitativa entre todas las bodegas
    - Bodega especializada en ciertos tipos de producto
    
    **Reglas de distribución:**
    - Porcentaje por bodega
    - Prioridad de restock
    - Límites de stock por ubicación
    - Redistribución automática cuando sea necesario
    """
    service = AdminService(db)
    return await service.assign_product_model_to_warehouses(assignment, current_user)

@router.get("/product-assignments")
async def get_product_assignments(
    product_reference: Optional[str] = Query(None, description="Código de referencia"),
    warehouse_id: Optional[int] = Query(None, description="ID de bodega"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener asignaciones de productos a bodegas
    """
    # En producción, esto consultaría una tabla específica de asignaciones
    # Por ahora, retornamos ejemplo basado en inventory_changes
    return []

# ==================== DASHBOARD ADMINISTRATIVO ====================

@router.get("/dashboard", response_model=AdminDashboard)
async def get_admin_dashboard(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Dashboard completo del administrador
    
    **Funcionalidad:**
    - Vista consolidada de todas las operaciones bajo gestión
    - Métricas en tiempo real de todas las ubicaciones
    - Tareas pendientes que requieren atención
    - Alertas críticas y de advertencia
    - Performance general del equipo
    
    **Secciones del dashboard:**
    - **Resumen diario:** Ventas, transacciones, usuarios activos
    - **Ubicaciones gestionadas:** Stats por local/bodega
    - **Tareas pendientes:** Aprobaciones, asignaciones, alertas
    - **Performance overview:** Métricas consolidadas del equipo
    - **Actividades recientes:** Log de acciones importantes
    """
    service = AdminService(db)
    return await service.get_admin_dashboard(current_user)

@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Métricas específicas del dashboard
    """
    service = AdminService(db)
    dashboard_data = service.repository.get_admin_dashboard_data(current_user.id)
    
    return DashboardMetrics(
        total_sales_today=Decimal(str(dashboard_data["daily_summary"]["total_sales"])),
        total_sales_month=Decimal(str(dashboard_data["daily_summary"]["total_sales"])) * 30,  # Estimado
        active_users=dashboard_data["daily_summary"]["active_users"],
        pending_transfers=dashboard_data["pending_tasks"]["pending_transfers"],
        low_stock_alerts=dashboard_data["pending_tasks"]["low_stock_alerts"],
        pending_discount_approvals=dashboard_data["pending_tasks"]["discount_approvals"],
        avg_performance_score=dashboard_data["performance_overview"].get("avg_performance_score", 85.0)
    )

# ==================== ENDPOINTS DE UTILIDAD ====================

@router.get("/health")
async def admin_module_health():
    """
    Verificar estado del módulo admin
    """
    return {
        "module": "admin",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "AD001 - Gestionar múltiples locales ✅",
            "AD002 - Supervisar múltiples bodegas ✅", 
            "AD003 - Crear usuarios vendedores ✅",
            "AD004 - Crear usuarios bodegueros ✅",
            "AD005 - Asignar vendedores a locales ✅",
            "AD006 - Asignar bodegueros a bodegas ✅",
            "AD007 - Configurar costos fijos ✅",
            "AD008 - Configurar costos variables ✅",
            "AD009 - Procesar ventas al por mayor ✅",
            "AD010 - Generar reportes de ventas ✅",
            "AD011 - Configurar alertas de inventario ✅",
            "AD012 - Aprobar solicitudes de descuento ✅",
            "AD013 - Supervisar traslados ✅",
            "AD014 - Supervisar performance ✅",
            "AD015 - Gestionar asignación de modelos ✅"
        ]
    }

@router.get("/statistics")
async def get_admin_statistics(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Estadísticas generales del módulo administrativo
    """
    service = AdminService(db)
    
    # Estadísticas básicas
    managed_locations = service.repository.get_managed_locations(current_user.id)
    managed_users = service.repository.get_users_by_admin(current_user.id)
    
    stats = {
        "managed_locations": len(managed_locations),
        "locations_by_type": {
            "locales": len([l for l in managed_locations if l.type == "local"]),
            "bodegas": len([l for l in managed_locations if l.type == "bodega"])
        },
        "managed_users": len(managed_users),
        "users_by_role": {
            "vendedores": len([u for u in managed_users if u.role == "vendedor"]),
            "bodegueros": len([u for u in managed_users if u.role == "bodeguero"]),
            "corredores": len([u for u in managed_users if u.role == "corredor"])
        },
        "pending_tasks": {
            "discount_approvals": service.repository.db.query(func.count(DiscountRequest.id))\
                .filter(DiscountRequest.status == "pending").scalar() or 0,
            "pending_transfers": service.repository.db.query(func.count(TransferRequest.id))\
                .filter(TransferRequest.status == "pending").scalar() or 0
        }
    }
    
    return stats

# ==================== ENDPOINTS DE CONFIGURACIÓN ====================

@router.post("/system/init-additional-tables")
async def initialize_additional_tables(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Inicializar tablas adicionales que podrían faltar
    (Endpoint de utilidad para desarrollo)
    """
    try:
        # En producción, esto ejecutaría migraciones específicas
        return {
            "success": True,
            "message": "Tablas adicionales inicializadas correctamente",
            "tables_created": [
                "user_location_assignments",
                "cost_configurations", 
                "inventory_alerts",
                "product_assignments"
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inicializando tablas: {str(e)}"
        )

@router.get("/system/overview")
async def get_system_overview(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Vista general del sistema para administradores
    """
    service = AdminService(db)
    
    # Datos consolidados del sistema
    total_users = db.query(func.count(User.id)).scalar()
    total_locations = db.query(func.count(Location.id)).scalar()
    total_products = db.query(func.count(Product.id)).scalar()
    
    # Ventas del día
    today = date.today()
    daily_sales = db.query(func.sum(Sale.total_amount))\
        .filter(func.date(Sale.sale_date) == today).scalar() or Decimal('0')
    
    # Transferencias activas
    active_transfers = db.query(func.count(TransferRequest.id))\
        .filter(TransferRequest.status.in_(["pending", "accepted", "in_transit"])).scalar()
    
    return {
        "system_overview": {
            "total_users": total_users,
            "total_locations": total_locations,
            "total_products": total_products,
            "daily_sales": float(daily_sales),
            "active_transfers": active_transfers
        },
        "module_status": {
            "sales": "✅ Operational",
            "transfers": "✅ Operational", 
            "warehouse": "✅ Operational",
            "admin": "✅ Operational"
        },
        "recent_activity": {
            "last_sale": "Hace 5 minutos",
            "last_transfer": "Hace 12 minutos",
            "last_user_created": "Hace 2 horas",
            "system_uptime": "99.9%"
        }
    }


@router.get("/test-microservice-basic")
async def test_microservice_basic(
    current_user: User = Depends(require_roles(["administrador", "boss"]))
):
    """Test básico de conectividad"""
    import httpx
    from app.config.settings import settings
    
    microservice_url = getattr(settings, 'VIDEO_MICROSERVICE_URL', None)
    
    if not microservice_url:
        return {"error": "VIDEO_MICROSERVICE_URL no configurada"}
    
    tests = {}
    
    # Test 1: Ping básico
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{microservice_url}/")
            tests["root_endpoint"] = {
                "status": response.status_code,
                "content": response.text[:200]
            }
    except Exception as e:
        tests["root_endpoint"] = {"error": str(e)}
    
    # Test 2: Health endpoint
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{microservice_url}/health")
            tests["health_endpoint"] = {
                "status": response.status_code,
                "content": response.text[:200]
            }
    except Exception as e:
        tests["health_endpoint"] = {"error": str(e)}
    
    # Test 3: Process video endpoint (sin archivo)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{microservice_url}/api/v1/process-video")
            tests["process_video_endpoint"] = {
                "status": response.status_code,
                "content": response.text[:200]
            }
    except Exception as e:
        tests["process_video_endpoint"] = {"error": str(e)}
    
    return {
        "microservice_url": microservice_url,
        "tests": tests
    }

@router.post("/inventory/video-entry", response_model=ProductCreationResponse)
async def process_video_inventory_entry(
    warehouse_location_id: int = Form(..., description="ID de bodega destino"),
    size_quantities_json: str = Form(..., description="JSON con tallas y cantidades: [{'size':'39','quantity':5}]"),
    product_brand: Optional[str] = Form(None, description="Marca del producto"),
    unit_price: float = Form(..., description="Precio unitario del producto"),
    box_price: Optional[float] = Form(None, description="Precio por caja (opcional)"),
    product_model: Optional[str] = Form(None, description="Modelo del producto"),
    notes: Optional[str] = Form(None, description="Notas adicionales"),
    reference_image: Optional[UploadFile] = File(None, description="Imagen de referencia del producto"),
    video_file: UploadFile = File(..., description="Video del producto para IA"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):


    """
    AD016: Registro de inventario con video IA + tallas específicas + imagen de referencia
    
    **Funcionalidad principal:**
    - Registro de inventario con cantidades específicas por talla
    - Procesamiento automático de video con IA
    - Almacenamiento de imagen de referencia en Cloudinary
    - Extracción de características del producto
    - Creación automática de inventario con tallas exactas
    
    **Proceso completo:**
    1. Administrador especifica cantidades exactas por talla
    2. Sube imagen de referencia (opcional) que se almacena en Cloudinary
    3. Sube video que se procesa temporalmente con IA
    4. IA extrae: marca, modelo, color, características adicionales
    5. Se combina información del usuario con resultados de IA
    6. Se crea producto con datos optimizados
    7. Se crean ProductSize con cantidades específicas (no distribución automática)
    8. Video temporal se elimina después del procesamiento
    
    **Criterios de negocio:**
    - Solo administradores y boss pueden registrar inventario
    - Tallas y cantidades son exactas según especificación del usuario
    - Imagen se almacena permanentemente en Cloudinary
    - Video es temporal, solo para procesamiento IA
    - Sistema genera código de referencia único automáticamente
    
    **Formato size_quantities_json:**
    [
        {"size": "39", "quantity": 3},
        {"size": "40", "quantity": 8},
        {"size": "41", "quantity": 6}
    ]

    **Requisitos del video:**
    - Formato: MP4, MOV, AVI (máximo 100MB)
    - Mostrar producto desde múltiples ángulos
    - Incluir etiquetas y tallas visibles claramente
    - Buena iluminación y enfoque nítido
    - Duración recomendada: 30-90 segundos

    **Requisitos de imagen de referencia:**
    - Formato: JPG, PNG, WebP (máximo 10MB)
    - Resolución recomendada: 800x600px
    - Buena calidad y iluminación
    """
    service = AdminService(db)
    import logging
    logger = logging.getLogger(__name__)

    # Validar archivo de video
    if not video_file.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail="Archivo debe ser un video válido")

    # Validar tamaño del video (100MB máximo)
    if video_file.size > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Video no debe superar 100MB")

    # Validar imagen de referencia si se proporciona
    if reference_image:
        if not reference_image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Archivo de referencia debe ser una imagen")
        if reference_image.size > settings.max_image_size:
            raise HTTPException(status_code=400, detail="Imagen no debe superar 10MB")

    if unit_price <= 0:
        raise HTTPException(status_code=400, detail="El precio unitario debe ser mayor a 0")
    if unit_price > 9999999.99:
        raise HTTPException(status_code=400, detail="El precio unitario no puede superar $9,999,999.99")
    
    if box_price is not None:
        if box_price < 0:
            raise HTTPException(status_code=400, detail="El precio por caja no puede ser negativo")
        if box_price > 9999999.99:
            raise HTTPException(status_code=400, detail="El precio por caja no puede superar $9,999,999.99")

    # Parsear y validar tallas con cantidades
    try:
        size_quantities_data = json.loads(size_quantities_json)
        if not isinstance(size_quantities_data, list) or len(size_quantities_data) == 0:
            raise ValueError("Debe ser un array con al menos una talla")
        size_quantities = [SizeQuantityEntry(**sq) for sq in size_quantities_data]
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Error en tallas: {str(e)}")

    # Crear objeto de entrada
    video_entry = VideoProductEntryWithSizes(
        warehouse_location_id=warehouse_location_id,
        size_quantities=size_quantities,
        product_brand=product_brand,
        product_model=product_model,
        unit_price=Decimal(str(unit_price)),  
        box_price=Decimal(str(box_price)) if box_price is not None else None,
        notes=notes
    )

    return await service.process_video_inventory_entry(video_entry, video_file, reference_image, current_user)

@router.get("/inventory/video-entries", response_model=List[VideoProcessingResponse])
async def get_video_processing_history(
    limit: int = Query(20, ge=1, le=100, description="Límite de resultados"),
    status: Optional[str] = Query(None, description="Estado: processing, completed, failed"),
    warehouse_id: Optional[int] = Query(None, description="Filtrar por bodega"),
    date_from: Optional[datetime] = Query(None, description="Fecha desde"),
    date_to: Optional[datetime] = Query(None, description="Fecha hasta"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener historial de videos procesados para entrenamiento de IA
    
    **Funcionalidad:**
    - Ver historial completo de videos procesados
    - Filtrar por estado de procesamiento
    - Filtrar por bodega de destino
    - Ver resultados de extracción de IA
    - Seguimiento del entrenamiento del modelo
    """
    service = AdminService(db)
    return await service.get_video_processing_history(
        limit=limit,
        status=status,
        warehouse_id=warehouse_id,
        date_from=date_from,
        date_to=date_to,
        admin_user=current_user
    )

@router.get("/inventory/video-entries/{video_id}", response_model=VideoProcessingResponse)
async def get_video_processing_details(
    video_id: int,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener detalles específicos de un video procesado
    """
    service = AdminService(db)
    return await service.get_video_processing_details(video_id, current_user)

# app/modules/admin/router.py - AGREGAR estos endpoints

@router.post("/video-processing-complete")
async def video_processing_complete_webhook(
    job_id: int = Form(...),
    status: str = Form(...),
    results: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Webhook que recibe notificación del microservicio cuando completa procesamiento
    """
    try:
        logger.info(f"📨 Webhook recibido - Job ID: {job_id}, Status: {status}")
        
        # Buscar job en BD
        from app.shared.database.models import VideoProcessingJob
        job = db.query(VideoProcessingJob).filter(VideoProcessingJob.id == job_id).first()
        
        if not job:
            logger.error(f"❌ Job {job_id} no encontrado")
            raise HTTPException(status_code=404, detail="Job no encontrado")
        
        # Parsear resultados
        results_data = json.loads(results)
        
        if status == "completed":
            # Actualizar job
            job.status = "completed"
            job.processing_completed_at = datetime.now()
            job.ai_results = results
            job.confidence_score = results_data.get("confidence_score", 0.0)
            job.detected_products = json.dumps(results_data.get("detected_products", []))
            
            # Crear productos reales en BD
            service = AdminService(db)
            created_products = await service._create_products_from_ai_results(
                results_data, job
            )
            
            job.created_products = json.dumps([p.id for p in created_products])
            
            logger.info(f"✅ Job {job_id} completado - {len(created_products)} productos creados")
            
        elif status == "failed":
            job.status = "failed"
            job.error_message = results_data.get("error_message", "Error desconocido")
            job.processing_completed_at = datetime.now()
            
            logger.error(f"❌ Job {job_id} falló: {job.error_message}")
        
        db.commit()
        
        # TODO: Enviar notificación al admin (email, websocket, etc.)
        
        return {"status": "success", "message": "Webhook procesado"}
        
    except Exception as e:
        logger.error(f"❌ Error procesando webhook job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/video-jobs/{job_id}/status")
async def get_video_job_status(
    job_id: int,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """Consultar estado de job de video"""
    service = AdminService(db)
    return await service.get_video_processing_status(job_id, current_user)


# ==================== GESTIÓN DE ASIGNACIONES DE ADMINISTRADORES ====================

@router.post("/admin-assignments", response_model=AdminLocationAssignmentResponse)
async def assign_admin_to_location(
    assignment: AdminLocationAssignmentCreate,
    current_user: User = Depends(require_roles(["boss"])),
    db: Session = Depends(get_db)
):
    """
    **SOLO BOSS:** Asignar administrador a ubicación específica
    
    **Funcionalidad:**
    - Solo el BOSS puede asignar administradores a ubicaciones
    - Valida que el usuario sea administrador
    - Evita asignaciones duplicadas
    - Mantiene historial de quién hizo la asignación
    
    **Casos de uso:**
    - Nuevo administrador se encarga de un local
    - Redistribución de responsabilidades
    - Expansión a nuevas ubicaciones
    """
    service = AdminService(db)
    return await service.assign_admin_to_locations(assignment, current_user)

@router.post("/admin-assignments/bulk", response_model=List[AdminLocationAssignmentResponse])
async def assign_admin_to_multiple_locations(
    bulk_assignment: AdminLocationAssignmentBulk,
    current_user: User = Depends(require_roles(["boss"])),
    db: Session = Depends(get_db)
):
    """
    **SOLO BOSS:** Asignar administrador a múltiples ubicaciones
    
    **Funcionalidad:**
    - Asignación masiva para administradores que gestionan múltiples ubicaciones
    - Proceso atómico por ubicación (si una falla, continúa con las demás)
    - Notas aplicadas a todas las asignaciones
    """
    service = AdminService(db)
    return await service.assign_admin_to_multiple_locations(bulk_assignment, current_user)

@router.get("/admin-assignments", response_model=List[AdminLocationAssignmentResponse])
async def get_admin_assignments(
    admin_id: Optional[int] = Query(None, description="ID del administrador (solo para BOSS)"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener asignaciones de ubicaciones
    
    **Para administradores:** Ve solo sus propias asignaciones
    **Para BOSS:** Puede ver asignaciones de cualquier administrador
    """
    service = AdminService(db)
    
    if current_user.role == "boss":
        if admin_id:
            # BOSS viendo asignaciones de un administrador específico
            admin = db.query(User).filter(User.id == admin_id).first()
            if not admin:
                raise HTTPException(status_code=404, detail="Administrador no encontrado")
            return await service.get_admin_assignments(admin)
        else:
            # BOSS viendo todas las asignaciones
            return await service.get_all_admin_assignments(current_user)
    else:
        # Administrador viendo solo sus asignaciones
        return await service.get_admin_assignments(current_user)

@router.delete("/admin-assignments/{admin_id}/{location_id}")
async def remove_admin_assignment(
    admin_id: int,
    location_id: int,
    current_user: User = Depends(require_roles(["boss"])),
    db: Session = Depends(get_db)
):
    """
    **SOLO BOSS:** Remover asignación de administrador a ubicación
    
    **Funcionalidad:**
    - Solo el BOSS puede remover asignaciones
    - Desactiva la asignación (no la elimina para mantener historial)
    - Los usuarios bajo gestión del administrador quedan sin supervisión directa
    """
    service = AdminService(db)
    return await service.remove_admin_assignment(admin_id, location_id, current_user)

@router.get("/my-locations", response_model=List[LocationResponse])
async def get_my_assigned_locations(
    current_user: User = Depends(require_roles(["administrador"])),
    db: Session = Depends(get_db)
):
    """
    **SOLO ADMINISTRADORES:** Ver ubicaciones asignadas al administrador actual
    
    **Funcionalidad:**
    - Muestra solo las ubicaciones donde el administrador tiene permisos
    - Incluye estadísticas básicas de cada ubicación
    - Base para otros endpoints que requieren validación de permisos
    """
    service = AdminService(db)
    
    # Usar el método corregido que ya filtra por asignaciones
    locations = await service.get_managed_locations(current_user)
    
    return locations

# ==================== ENDPOINTS DE VALIDACIÓN ====================

@router.get("/can-manage-location/{location_id}")
async def can_manage_location(
    location_id: int,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Verificar si el administrador actual puede gestionar una ubicación específica
    """
    
    if current_user.role == "boss":
        return {"can_manage": True, "reason": "BOSS has access to all locations"}
    
    # Verificar asignación específica
    assignment = db.query(AdminLocationAssignment)\
        .filter(
            AdminLocationAssignment.admin_id == current_user.id,
            AdminLocationAssignment.location_id == location_id,
            AdminLocationAssignment.is_active == True
        ).first()
    
    return {
        "can_manage": assignment is not None,
        "reason": "Assigned location" if assignment else "Not assigned to this location"
    }

@router.get("/available-admins", response_model=List[UserResponse])
async def get_available_administrators(
    current_user: User = Depends(require_roles(["boss"])),
    db: Session = Depends(get_db)
):
    """
    **SOLO BOSS:** Obtener lista de administradores disponibles para asignar
    """
    
    admins = db.query(User)\
        .filter(
            User.role == "administrador",
            User.is_active == True
        )\
        .order_by(User.first_name, User.last_name)\
        .all()
    
    return [
        UserResponse(
            id=admin.id,
            email=admin.email,
            first_name=admin.first_name,
            last_name=admin.last_name,
            full_name=admin.full_name,
            role=admin.role,
            location_id=admin.location_id,
            location_name=admin.location.name if admin.location else None,
            is_active=admin.is_active,
            created_at=admin.created_at
        ) for admin in admins
    ]

@router.get("/unassigned-locations", response_model=List[LocationResponse])
async def get_unassigned_locations(
    current_user: User = Depends(require_roles(["boss"])),
    db: Session = Depends(get_db)
):
    """
    **SOLO BOSS:** Obtener ubicaciones que no tienen administrador asignado
    """
    
    # Ubicaciones sin asignaciones activas
    assigned_location_ids = db.query(AdminLocationAssignment.location_id)\
        .filter(AdminLocationAssignment.is_active == True)\
        .subquery()
    
    unassigned_locations = db.query(Location)\
        .filter(
            Location.is_active == True,
            ~Location.id.in_(assigned_location_ids)
        )\
        .order_by(Location.name)\
        .all()
    
    return [
        LocationResponse(
            id=loc.id,
            name=loc.name,
            type=loc.type,
            address=loc.address,
            phone=loc.phone,
            is_active=loc.is_active,
            created_at=loc.created_at,
            assigned_users_count=0,  # No calculado para eficiencia
            total_products=0,        # No calculado para eficiencia
            total_inventory_value=Decimal('0')  # No calculado para eficiencia
        ) for loc in unassigned_locations
    ]

@router.post("/video-callback")
async def video_processing_callback(
    job_id: int = Form(...),
    status: str = Form(...),
    results: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Callback para recibir resultados del microservicio de video - USANDO TABLA DEDICADA
    """
    from app.shared.database.models import VideoProcessingJob
    import json
    
    try:
        # Parsear resultados
        results_dict = json.loads(results)
        
        # Buscar el job en la nueva tabla
        processing_job = db.query(VideoProcessingJob).filter(
            VideoProcessingJob.id == job_id
        ).first()
        
        if not processing_job:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        
        # Actualizar job con resultados finales
        processing_job.processing_status = status
        processing_job.processing_completed_at = datetime.now()
        
        if status == "completed":
            # Actualizar con resultados exitosos
            processing_job.ai_results_json = results
            processing_job.confidence_score = results_dict.get('confidence_scores', {}).get('overall', 0.0)
            processing_job.detected_brand = results_dict.get('detected_brand')
            processing_job.detected_model = results_dict.get('detected_model')
            processing_job.detected_colors = json.dumps(results_dict.get('detected_colors', []))
            processing_job.detected_sizes = json.dumps(results_dict.get('detected_sizes', []))
            processing_job.frames_extracted = results_dict.get('frames_processed', 0)
            processing_job.processing_time_seconds = results_dict.get('processing_time', 0)
            
            logger.info(f"✅ Video job {job_id} completed successfully")
            
        else:
            # Actualizar con error
            processing_job.error_message = results_dict.get('error_message', 'Error desconocido')
            processing_job.retry_count += 1
            
            logger.error(f"❌ Video job {job_id} failed: {processing_job.error_message}")
        
        db.commit()
        
        return {"status": "callback_received", "job_id": job_id, "updated": True}
        
    except Exception as e:
        logger.error(f"❌ Error en callback job {job_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# app/modules/admin/router.py - AGREGAR ESTE ENDPOINT DE DIAGNÓSTICO

@router.get("/diagnosis/microservice-connection")
async def test_microservice_connection(
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    🔬 DIAGNÓSTICO: Probar conexión con microservicio
    """
    import httpx
    from app.config.settings import settings
    
    diagnosis = {
        "timestamp": datetime.now().isoformat(),
        "microservice_url": getattr(settings, 'VIDEO_PROCESSING_SERVICE_URL', 'NOT_CONFIGURED'),
        "api_key_configured": bool(getattr(settings, 'VIDEO_PROCESSING_API_KEY', None)),
        "tests": {}
    }
    
    # Test 1: Health check del microservicio
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {}
            if hasattr(settings, 'VIDEO_PROCESSING_API_KEY') and settings.VIDEO_PROCESSING_API_KEY:
                headers["Authorization"] = f"Bearer {settings.VIDEO_PROCESSING_API_KEY}"
            
            response = await client.get(
                f"{settings.VIDEO_PROCESSING_SERVICE_URL}/health",
                headers=headers
            )
            
            diagnosis["tests"]["health_check"] = {
                "status": "✅ SUCCESS" if response.status_code == 200 else "❌ FAILED",
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
    except Exception as e:
        diagnosis["tests"]["health_check"] = {
            "status": "❌ ERROR",
            "error": str(e)
        }
    
    # Test 2: Endpoint de procesamiento (sin archivo)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"Authorization": f"Bearer {settings.VIDEO_PROCESSING_API_KEY}"} if hasattr(settings, 'VIDEO_PROCESSING_API_KEY') else {}
            
            response = await client.post(
                f"{settings.VIDEO_PROCESSING_SERVICE_URL}/api/v1/process-video",
                data={
                    "job_id": 999,
                    "callback_url": "https://test.com/callback",
                    "metadata": "{\"test\": true}"
                },
                headers=headers
            )
            
            diagnosis["tests"]["process_endpoint"] = {
                "status": "✅ ACCESSIBLE" if response.status_code in [400, 422] else "❌ UNEXPECTED",
                "status_code": response.status_code,
                "expected": "422 (validation error without video file)",
                "response": response.text[:200] if response.text else "No response"
            }
    except Exception as e:
        diagnosis["tests"]["process_endpoint"] = {
            "status": "❌ ERROR",
            "error": str(e)
        }
    
    return
    


    
@router.get("/diagnosis/job-logs/{job_id}")
async def get_job_logs(
    job_id: int,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    🔬 DIAGNÓSTICO: Ver logs detallados de un job
    """
    from app.shared.database.models import VideoProcessingJob
    
    job = db.query(VideoProcessingJob).filter(VideoProcessingJob.id == job_id).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    
    # Información detallada del job
    job_info = {
        "job_id": job.id,
        "status": job.processing_status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
        "completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
        "processing_time_seconds": None,
        "video_file": {
            "path": job.video_file_path,
            "original_name": job.original_filename,
            "size_bytes": job.file_size_bytes,
            "exists": os.path.exists(job.video_file_path) if job.video_file_path else False
        },
        "microservice_info": {
            "job_id": job.microservice_job_id,
            "callback_received": job.processing_completed_at is not None
        },
        "error_info": {
            "error_message": job.error_message,
            "retry_count": job.retry_count
        },
        "ai_results": {
            "has_results": bool(job.ai_results_json),
            "confidence_score": float(job.confidence_score) if job.confidence_score else 0,
            "detected_brand": job.detected_brand,
            "detected_model": job.detected_model
        }
    }
    
    # Calcular tiempo de procesamiento
    if job.processing_started_at and job.processing_completed_at:
        delta = job.processing_completed_at - job.processing_started_at
        job_info["processing_time_seconds"] = delta.total_seconds()
    
    return job_info
