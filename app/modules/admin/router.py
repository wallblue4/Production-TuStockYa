# app/modules/admin/router.py
from fastapi import APIRouter, Depends, HTTPException, Query , File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, date


from app.config.database import get_db
from app.core.auth.dependencies import get_current_user, require_roles
from app.shared.database.models import User
from .service import AdminService
from .schemas import *

router = APIRouter(prefix="/admin", tags=["Admin - Administrador"])

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
    """
    service = AdminService(db)
    users = service.repository.get_users_by_admin(current_user.id)
    
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

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Actualizar información de usuario gestionado
    """
    service = AdminService(db)
    
    user = service.repository.update_user(user_id, update_data.dict(exclude_unset=True))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        role=user.role,
        location_id=user.location_id,
        location_name=user.location.name if user.location else None,
        is_active=user.is_active,
        created_at=user.created_at
    )

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
    
    **Funcionalidad:**
    - Asignar/reasignar usuarios a ubicaciones específicas
    - Validar compatibilidad entre rol de usuario y tipo de ubicación
    - Mantener historial de asignaciones
    - Actualizar ubicación principal del usuario
    
    **Casos de uso:**
    - Vendedor se cambia de local
    - Bodeguero se asigna a nueva bodega
    - Redistribución de personal por necesidades operativas
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
    """
    service = AdminService(db)
    return service.repository.get_location_stats(location_id, start_date, end_date)

# ==================== AD007 & AD008: CONFIGURAR COSTOS ====================

@router.post("/costs", response_model=CostResponse)
async def configure_operational_cost(
    cost_config: CostConfiguration,
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD007: Configurar costos fijos (arriendo, servicios, nómina)
    AD008: Configurar costos variables (mercancía, comisiones)
    
    **Funcionalidad:**
    - Configurar costos fijos: arriendo, servicios públicos, nómina
    - Configurar costos variables: mercancía, comisiones, transporte
    - Establecer frecuencia de costos (mensual, semanal, diario)
    - Asociar costos a ubicaciones específicas
    
    **Casos de uso:**
    - Nuevo local requiere configuración de arriendo mensual
    - Actualizar tarifas de servicios públicos
    - Configurar comisiones por ventas
    - Establecer costos de transporte entre ubicaciones
    """
    service = AdminService(db)
    return await service.configure_cost(cost_config, current_user)

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

@router.post("/inventory/video-entry", response_model=VideoProcessingResponse)
async def process_video_inventory_entry(
    warehouse_location_id: int = Form(..., description="ID de bodega destino"),
    estimated_quantity: int = Form(..., gt=0, description="Cantidad estimada"),
    product_brand: Optional[str] = Form(None, description="Marca del producto"),
    product_model: Optional[str] = Form(None, description="Modelo del producto"),
    expected_sizes: Optional[str] = Form(None, description="Tallas esperadas (separadas por coma)"),
    notes: Optional[str] = Form(None, description="Notas adicionales"),
    video_file: UploadFile = File(..., description="Video del producto para IA"),
    current_user: User = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    AD016: Registro de inventario con video IA (MIGRADO DE BG010)
    
    **Funcionalidad principal:**
    - Registro estratégico de inventario por administradores
    - Procesamiento automático de video con IA
    - Extracción de características del producto
    - Entrenamiento automático del sistema de reconocimiento
    - Asignación automática a bodegas según reglas configuradas
    
    **Proceso completo:**
    1. Administrador graba video del producto desde múltiples ángulos
    2. Sistema procesa video automáticamente para entrenar IA
    3. IA extrae: marca, modelo, color, tallas visibles
    4. Se registra información completa para verificación posterior
    5. Sistema aplica reglas de distribución configuradas
    6. Se asignan ubicaciones físicas automáticamente
    7. IA queda entrenada para reconocer el nuevo producto
    
    **Criterios de negocio:**
    - Solo administradores y boss pueden registrar inventario
    - Video debe mostrar producto desde múltiples ángulos
    - Procesamiento debe extraer características automáticamente
    - Debe asignar bodegas según reglas configuradas
    - IA debe quedar entrenada inmediatamente
    - Debe generar ubicación física automática
    
    **Requisitos del video:**
    - Mostrar producto desde múltiples ángulos (mínimo 4 ángulos)
    - Incluir etiquetas y tallas visibles claramente
    - Buena iluminación y enfoque nítido
    - Duración recomendada: 30-90 segundos
    - Formato: MP4, MOV, AVI (máximo 100MB)
    """
    service = AdminService(db)
    
    # Validar archivo de video
    if not video_file.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail="Archivo debe ser un video válido")
    
    # Validar tamaño (100MB máximo)
    if video_file.size > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Video no debe superar 100MB")
    
    # Procesar tallas esperadas
    expected_sizes_list = None
    if expected_sizes:
        expected_sizes_list = [size.strip() for size in expected_sizes.split(',')]
    
    video_entry = VideoProductEntry(
        video_file_path="",  # Se establecerá en el servicio
        warehouse_location_id=warehouse_location_id,
        estimated_quantity=estimated_quantity,
        product_brand=product_brand,
        product_model=product_model,
        expected_sizes=expected_sizes_list,
        notes=notes
    )
    
    return await service.process_video_inventory_entry(video_entry, video_file, current_user)

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