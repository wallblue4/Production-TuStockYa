from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import get_current_user, require_roles
from app.core.auth.schemas import UserResponse
from app.modules.transfers.service import TransferService
from app.modules.transfers.schemas import (
    TransferRequestCreate, TransferAcceptance, CourierAcceptance,
    PickupConfirmation, DeliveryConfirmation, ReceptionConfirmation,
    TransferRequestResponse, TransferDashboard, TransportIncidentCreate,
    TransferStatus
)

router = APIRouter(prefix="/transfers", tags=["Transfers"])

# ===== VENDEDOR ENDPOINTS =====

@router.post("/request", response_model=TransferRequestResponse)
async def create_transfer_request(
    request_data: TransferRequestCreate,
    current_user: UserResponse = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE003: Solicitar productos de otras ubicaciones
    
    **Funcionalidad:**
    - Crear solicitud de transferencia especificando producto, cantidad y urgencia
    - Validar disponibilidad antes de crear la solicitud
    - Establecer prioridad según si es para cliente presente o restock
    
    **Casos de uso:**
    - Vendedor tiene cliente esperando producto que no está en su local
    - Solicitar productos para restock de exhibición
    - Transferencia entre bodegas
    """
    service = TransferService(db)
    return service.create_transfer_request(request_data, current_user)


@router.get("/my-requests", response_model=List[TransferRequestResponse])
async def get_my_transfer_requests(
    status: Optional[List[TransferStatus]] = Query(None, description="Filtrar por estados"),
    current_user: UserResponse = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener mis solicitudes de transferencia
    
    **Filtros disponibles:**
    - status: Lista de estados para filtrar (pending, accepted, in_transit, etc.)
    """
    service = TransferService(db)
    status_filter = [s.value for s in status] if status else None
    return service.get_my_transfer_requests(current_user, status_filter)


@router.get("/pending-receptions", response_model=List[TransferRequestResponse])
async def get_pending_receptions(
    current_user: UserResponse = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE008: Ver productos entregados pendientes de confirmación de recepción
    
    **Funcionalidad:**
    - Mostrar transferencias en estado 'delivered' que requieren confirmación
    - Incluir información del corredor que entregó
    - Mostrar tiempo transcurrido desde la entrega
    """
    service = TransferService(db)
    return service.get_pending_receptions(current_user)


@router.post("/{transfer_id}/confirm-reception")
async def confirm_reception(
    transfer_id: int,
    confirmation: ReceptionConfirmation,
    current_user: UserResponse = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE008: Confirmar recepción de productos solicitados
    
    **Funcionalidad:**
    - Registrar hora de recepción
    - Verificar cantidad y estado de productos recibidos
    - Actualizar inventario local automáticamente
    - Marcar transferencia como completada
    
    **Validaciones:**
    - Solo el vendedor solicitante puede confirmar
    - Transferencia debe estar en estado 'delivered'
    - Actualización automática de inventario en caso exitoso
    """
    service = TransferService(db)
    return service.confirm_reception(transfer_id, confirmation, current_user)


@router.post("/{transfer_id}/cancel")
async def cancel_transfer_request(
    transfer_id: int,
    reason: Optional[str] = "Cancelada por vendedor",
    current_user: UserResponse = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Cancelar solicitud de transferencia
    
    **Restricciones:**
    - Solo se puede cancelar si está en estado 'pending' o 'accepted'
    - Solo el vendedor solicitante puede cancelar
    - Una vez asignado corredor, no se puede cancelar
    """
    service = TransferService(db)
    return service.cancel_transfer_request(transfer_id, current_user, reason)


# ===== BODEGUERO ENDPOINTS =====

@router.get("/warehouse/pending", response_model=List[TransferRequestResponse])
async def get_pending_requests_for_warehouse(
    current_user: UserResponse = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG001: Recibir y procesar solicitudes de productos
    
    **Funcionalidad:**
    - Ver solicitudes pendientes para ubicaciones asignadas al bodeguero
    - Información visible: foto, referencia, local solicitante, hora, talla, cantidad, propósito
    - Ordenadas por prioridad: cliente presente primero, luego por hora de solicitud
    
    **Casos de uso:**
    - Bodeguero revisa solicitudes al inicio del turno
    - Priorizar atención a clientes presenciales
    - Verificar disponibilidad antes de aceptar
    """
    service = TransferService(db)
    return service.get_pending_requests_for_warehouse(current_user)


@router.get("/warehouse/accepted", response_model=List[TransferRequestResponse])
async def get_accepted_requests_by_warehouse(
    current_user: UserResponse = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG002: Ver solicitudes aceptadas y en preparación
    
    **Funcionalidad:**
    - Mostrar solicitudes aceptadas por este bodeguero
    - Estados: accepted, courier_assigned, in_transit
    - Información de corredor asignado cuando disponible
    """
    service = TransferService(db)
    return service.get_accepted_requests_by_warehouse(current_user)


@router.post("/warehouse/accept", response_model=TransferRequestResponse)
async def accept_transfer_request(
    acceptance: TransferAcceptance,
    current_user: UserResponse = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG002: Confirmar disponibilidad y preparar productos
    
    **Funcionalidad:**
    - Aceptar o rechazar solicitud de transferencia
    - Verificar stock disponible antes de aceptar
    - Establecer tiempo estimado de preparación
    - Una vez aceptada, queda disponible para corredores
    
    **Validaciones:**
    - Solo bodegueros asignados a la ubicación pueden aceptar
    - Verificación de stock en tiempo real
    - Solicitud debe estar en estado 'pending'
    """
    service = TransferService(db)
    return service.accept_transfer_request(acceptance, current_user)


@router.post("/{transfer_id}/deliver-to-courier")
async def deliver_to_courier(
    transfer_id: int,
    delivery: DeliveryConfirmation,
    current_user: UserResponse = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG003: Entregar productos a corredor
    
    **Funcionalidad CRÍTICA:**
    - Entregar producto físicamente al corredor
    - **Descuento automático de inventario** (requerimiento BG003)
    - Cambiar estado a 'in_transit'
    - Registrar timestamp de entrega
    
    **Proceso:**
    1. Corredor llega a bodega
    2. Bodeguero entrega producto
    3. Sistema descuenta inventario automáticamente
    4. Transferencia pasa a estado 'in_transit'
    
    **Casos de falla:**
    - Si entrega falla, activar proceso de reversión (BG010)
    """
    service = TransferService(db)
    return service.deliver_to_courier(transfer_id, delivery, current_user)


# ===== CORREDOR ENDPOINTS =====

@router.get("/courier/available", response_model=List[TransferRequestResponse])
async def get_available_requests_for_courier(
    current_user: UserResponse = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO001: Recibir notificaciones de solicitudes de transporte
    
    **Funcionalidad:**
    - Ver solicitudes disponibles para transporte
    - Incluye solicitudes aceptadas por bodegueros (sin corredor asignado)
    - Incluye solicitudes ya asignadas a este corredor
    - Información: foto del producto, referencia, punto de recolección, destino
    
    **Estados mostrados:**
    - 'accepted': Disponibles para aceptar
    - 'courier_assigned': Ya asignadas a este corredor
    - 'in_transit': En proceso de entrega por este corredor
    """
    service = TransferService(db)
    return service.get_available_requests_for_courier(current_user)


@router.post("/{transfer_id}/accept-courier")
async def accept_courier_request(
    transfer_id: int,
    acceptance: CourierAcceptance,
    current_user: UserResponse = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO002: Aceptar solicitud e iniciar recorrido
    
    **Funcionalidad:**
    - Aceptar transporte de una solicitud específica
    - Asignar corredor a la transferencia
    - Establecer tiempo estimado de llegada a recolección
    - Cambiar estado a 'courier_assigned'
    
    **Concurrencia:**
    - Solo un corredor puede aceptar cada solicitud
    - Sistema previene race conditions
    - Si otro corredor ya aceptó, devuelve error 409
    """
    service = TransferService(db)
    return service.accept_courier_request(transfer_id, acceptance, current_user)


@router.post("/{transfer_id}/confirm-pickup")
async def confirm_pickup(
    transfer_id: int,
    confirmation: PickupConfirmation,
    current_user: UserResponse = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO003: Confirmar recolección en bodega (registrar hora)
    
    **Funcionalidad:**
    - Confirmar que se recogió el producto en bodega
    - Registrar timestamp exacto de recolección
    - Cambiar estado a 'in_transit'
    - Agregar notas sobre la recolección
    
    **Validaciones:**
    - Solo el corredor asignado puede confirmar
    - Transferencia debe estar en estado 'courier_assigned'
    """
    service = TransferService(db)
    return service.confirm_pickup(transfer_id, confirmation, current_user)


@router.post("/{transfer_id}/confirm-delivery")
async def confirm_delivery(
    transfer_id: int,
    confirmation: DeliveryConfirmation,
    current_user: UserResponse = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO004: Confirmar entrega en local (registrar hora)
    
    **Funcionalidad:**
    - Confirmar entrega exitosa o fallida en destino
    - Registrar timestamp exacto de entrega
    - Cambiar estado a 'delivered' o 'delivery_failed'
    
    **Casos:**
    - Entrega exitosa: Estado 'delivered', vendedor debe confirmar recepción
    - Entrega fallida: Estado 'delivery_failed', activar reversión de inventario
    
    **CO007: Notificar entrega fallida**
    - Si delivery_successful = false, activa proceso de reversión automática
    """
    service = TransferService(db)
    return service.confirm_delivery(transfer_id, confirmation, current_user)


@router.post("/{transfer_id}/report-incident")
async def report_transport_incident(
    transfer_id: int,
    incident: TransportIncidentCreate,
    current_user: UserResponse = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO005: Reportar incidencias durante el transporte
    
    **Funcionalidad:**
    - Reportar problemas durante el transporte
    - Crear registro de incidencia para seguimiento
    - Mantener trazabilidad de problemas
    
    **Tipos de incidencias:**
    - Producto dañado durante transporte
    - Retraso por tráfico/clima
    - Problemas de acceso al destino
    - Cliente no disponible en destino
    """
    service = TransferService(db)
    return service.report_incident(transfer_id, incident, current_user)


@router.get("/courier/delivery-history", response_model=List[TransferRequestResponse])
async def get_courier_delivery_history(
    current_user: UserResponse = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO006: Consultar historial de entregas realizadas
    
    **Funcionalidad:**
    - Ver histórico completo de entregas del corredor
    - Incluir entregas exitosas y fallidas
    - Métricas de performance personal
    - Filtrado por fechas y estados
    """
    service = TransferService(db)
    return service.get_courier_delivery_history(current_user)


# ===== DASHBOARD Y MÉTRICAS =====

@router.get("/dashboard", response_model=TransferDashboard)
async def get_transfer_dashboard(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Dashboard de transferencias personalizado por rol
    
    **Funcionalidad por rol:**
    
    **Vendedor:**
    - Mis solicitudes activas
    - Entregas pendientes de confirmación
    - Estado de transferencias urgentes
    
    **Bodeguero:**
    - Solicitudes pendientes de aceptación
    - Solicitudes aceptadas en preparación
    - Productos listos para entrega a corredor
    
    **Corredor:**
    - Solicitudes disponibles para transporte
    - Mis transportes en curso
    - Entregas programadas del día
    
    **Administrador:**
    - Vista consolidada de todas las transferencias
    - Métricas de eficiencia del sistema
    - Alertas de demoras y problemas
    """
    service = TransferService(db)
    return service.get_transfer_dashboard(current_user)


@router.get("/{transfer_id}", response_model=TransferRequestResponse)
async def get_transfer_by_id(
    transfer_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtener detalles específicos de una transferencia
    
    **Funcionalidad:**
    - Ver información completa de una transferencia
    - Incluir timeline de eventos
    - Mostrar participantes y sus acciones
    - Permisos según rol del usuario
    """
    service = TransferService(db)
    transfer = service.repository.get_transfer_by_id(transfer_id)
    
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transferencia no encontrada"
        )
    
    # Verificar permisos de acceso
    if not service.repository.can_user_access_transfer(transfer_id, current_user.id, current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para ver esta transferencia"
        )
    
    return service._build_transfer_response(transfer, current_user)


# ===== ENDPOINTS ADMINISTRATIVOS =====

@router.get("/admin/metrics")
async def get_transfer_metrics(
    date_from: Optional[datetime] = Query(None, description="Fecha inicio del reporte"),
    date_to: Optional[datetime] = Query(None, description="Fecha fin del reporte"),
    current_user: UserResponse = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Métricas administrativas del sistema de transferencias
    
    **Métricas incluidas:**
    - Volumen de transferencias por día/semana/mes
    - Tiempo promedio de procesamiento
    - Tasa de éxito/falla de entregas
    - Productos más solicitados
    - Performance por corredor y bodeguero
    - Alertas de demoras y problemas
    """
    service = TransferService(db)
    
    # Por defecto, métricas del día actual
    if not date_from:
        date_from = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    metrics = service.repository.get_daily_transfer_metrics(date_from)
    
    return {
        "success": True,
        "date_range": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat() if date_to else datetime.now().isoformat()
        },
        "metrics": metrics
    }


@router.get("/admin/status/{status}", response_model=List[TransferRequestResponse])
async def get_transfers_by_status(
    status: TransferStatus,
    current_user: UserResponse = Depends(require_roles(["administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener todas las transferencias por estado específico
    
    **Uso administrativo:**
    - Monitorear transferencias atascadas
    - Identificar cuellos de botella
    - Intervenir en casos problemáticos
    """
    service = TransferService(db)
    transfers = service.repository.get_transfers_by_status(status.value)
    
    return [service._build_transfer_response(t, current_user) for t in transfers]