# app/modules/courier/router.py
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import CourierService
from .schemas import (
    CourierAcceptance, PickupConfirmation, DeliveryConfirmation, TransportIncidentReport,
    AvailableRequestsResponse, MyTransportsResponse, DeliveryHistoryResponse
)

router = APIRouter()

@router.get("/available-requests", response_model=AvailableRequestsResponse)
async def get_available_requests(
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO001: Recibir notificaciones de solicitudes de transporte
    
    **Funcionalidad:**
    - Ver solicitudes disponibles para transporte
    - Incluye solicitudes aceptadas por bodegueros (sin corredor asignado)
    - Incluye solicitudes ya asignadas a este corredor
    - Vista unificada de transferencias y devoluciones
    
    **Información incluida:**
    - Foto del producto y descripción completa
    - Punto de recolección con contacto del bodeguero
    - Punto de entrega con contacto del solicitante
    - Nivel de urgencia y prioridad
    - Contexto de la ruta (transferencia vs devolución)
    """
    service = CourierService(db)
    
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name
    }
    
    return await service.get_available_requests(current_user.id, user_info)

@router.post("/accept-request/{request_id}")
async def accept_request(
    request_id: int = Path(..., description="ID de la solicitud"),
    acceptance: CourierAcceptance = CourierAcceptance(),
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
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
    - Primera llegada toma la solicitud
    """
    service = CourierService(db)
    return await service.accept_request(request_id, acceptance, current_user.id)

@router.post("/confirm-pickup/{request_id}")
async def confirm_pickup(
    request_id: int = Path(..., description="ID de la solicitud"),
    pickup_data: PickupConfirmation = PickupConfirmation(),
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO003: Confirmar recolección
    
    **Funcionalidad:**
    - Confirmar que se recogió el producto del bodeguero
    - Cambiar estado a 'in_transit'
    - Registrar timestamp de recolección
    - Iniciar tracking de entrega
    
    **Validaciones:**
    - Solo el corredor asignado puede confirmar
    - Solicitud debe estar en estado 'courier_assigned'
    """
    service = CourierService(db)
    return await service.confirm_pickup(request_id, pickup_data, current_user.id)

@router.post("/confirm-delivery/{request_id}")
async def confirm_delivery(
    request_id: int = Path(..., description="ID de la solicitud"),
    delivery_data: DeliveryConfirmation = DeliveryConfirmation(),
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO004: Confirmar entrega
    
    **Funcionalidad:**
    - Confirmar entrega exitosa o con problemas
    - Cambiar estado a 'delivered' o 'delivery_failed'
    - Registrar timestamp de entrega
    - Permitir al vendedor confirmar recepción
    
    **Casos de uso:**
    - Entrega exitosa: Producto entregado en buenas condiciones
    - Entrega con problemas: Daños, cliente ausente, dirección incorrecta
    """
    service = CourierService(db)
    return await service.confirm_delivery(request_id, delivery_data, current_user.id)

@router.post("/report-incident")
async def report_incident(
    request_id: int,
    incident_data: TransportIncidentReport,
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO005: Reportar incidencias durante el transporte
    
    **Tipos de incidencia:**
    - Problema de tráfico o ruta
    - Daño del producto durante transporte
    - Cliente no disponible
    - Dirección incorrecta
    - Problema con vehículo
    - Situación de seguridad
    
    **Proceso:**
    - Incidencia queda registrada para supervisión
    - Corredor puede continuar con entrega si es posible
    - Soporte revisa y da seguimiento
    """
    service = CourierService(db)
    return await service.report_incident(request_id, incident_data, current_user.id)

@router.get("/my-transports", response_model=MyTransportsResponse)
async def get_my_transports(
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener transportes asignados al corredor
    
    **Incluye:**
    - Transportes en progreso
    - Transportes completados
    - Estadísticas de performance
    - Información de tiempos
    """
    service = CourierService(db)
    
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name
    }
    
    return await service.get_my_transports(current_user.id, user_info)

@router.get("/my-deliveries", response_model=DeliveryHistoryResponse)
async def get_my_deliveries(
    current_user = Depends(require_roles(["corredor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    CO006: Historial de entregas del día
    
    **Funcionalidad:**
    - Entregas completadas del día
    - Estadísticas de éxito/fallo
    - Métricas de performance
    - Evaluación de eficiencia
    """
    service = CourierService(db)
    
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name
    }
    
    return await service.get_delivery_history(current_user.id, user_info)

@router.get("/health")
async def courier_health():
    """Health check del módulo courier"""
    return {
        "service": "courier",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "CO001 - Solicitudes disponibles",
            "CO002 - Aceptar transporte",
            "CO003 - Confirmar recolección",
            "CO004 - Confirmar entrega",
            "CO005 - Reportar incidencias",
            "CO006 - Historial de entregas",
            "Vista unificada transferencias/devoluciones",
            "Sistema de concurrencia",
            "Tracking completo de estado"
        ]
    }