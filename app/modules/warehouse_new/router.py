
# app/modules/warehouse_new/router.py
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import WarehouseService
from .schemas import (
    WarehouseRequestAcceptance, CourierDelivery, 
    PendingRequestsResponse, AcceptedRequestsResponse, InventoryByLocationResponse
)

router = APIRouter()

@router.get("/pending-requests", response_model=PendingRequestsResponse)
async def get_pending_requests(
    current_user = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG001: Recibir y procesar solicitudes de productos
    
    **Funcionalidad:**
    - Lista unificada de transferencias y devoluciones pendientes
    - Priorización automática (cliente > restock)
    - Información completa del producto y stock disponible
    - Tiempo transcurrido desde solicitud
    - Vista por ubicaciones asignadas al bodeguero
    
    **Información incluida:**
    - Detalles del producto (imagen, precio, stock)
    - Información del solicitante
    - Ubicaciones origen y destino
    - Nivel de urgencia y prioridad
    """
    service = WarehouseService(db)
    
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name
    }
    
    return await service.get_pending_requests(current_user.id, user_info)

@router.post("/accept-request")
async def accept_request(
    acceptance: WarehouseRequestAcceptance,
    current_user = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG002: Confirmar disponibilidad y preparar productos
    
    **Funcionalidad:**
    - Aceptar o rechazar solicitud después de verificar stock
    - Establecer tiempo estimado de preparación
    - Una vez aceptada, queda disponible para corredores
    - Actualizar estado y asignar bodeguero responsable
    
    **Validaciones:**
    - Solo bodegueros asignados a la ubicación pueden aceptar
    - Verificación de disponibilidad de stock
    - Solicitud debe estar en estado 'pending'
    """
    service = WarehouseService(db)
    return await service.accept_request(acceptance, current_user.id)

@router.get("/accepted-requests", response_model=AcceptedRequestsResponse)
async def get_accepted_requests(
    current_user = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Ver solicitudes aceptadas y en preparación
    
    **Funcionalidad:**
    - Solicitudes aceptadas por este bodeguero
    - Estados: accepted, courier_assigned, in_transit
    - Información de corredor asignado cuando disponible
    - Productos listos para entrega
    """
    service = WarehouseService(db)
    
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name
    }
    
    return await service.get_accepted_requests(current_user.id, user_info)

@router.post("/deliver-to-courier")
async def deliver_to_courier(
    delivery: CourierDelivery,
    current_user = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG003: Entregar productos a corredor
    
    **Funcionalidad CRÍTICA:**
    - Entregar producto físicamente al corredor
    - **Descuento automático de inventario** (requerimiento BG003)
    - Cambiar estado a 'in_transit'
    - Registrar timestamp de entrega
    - Actualizar historial de movimientos
    
    **Proceso:**
    1. Corredor llega a bodega
    2. Bodeguero entrega producto
    3. Sistema descuenta inventario automáticamente
    4. Producto queda en tránsito hacia destino
    """
    service = WarehouseService(db)
    return await service.deliver_to_courier(delivery, current_user.id)

@router.get("/inventory-by-location/{location_id}", response_model=InventoryByLocationResponse)
async def get_inventory_by_location(
    location_id: int = Path(..., description="ID de la ubicación"),
    current_user = Depends(require_roles(["bodeguero", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    BG006: Consultar inventario disponible por ubicación general
    
    **Funcionalidad:**
    - Inventario completo de una ubicación específica
    - Información detallada de cada producto
    - Stock disponible y en exhibición
    - Precios unitarios y por caja
    - Valor total del inventario
    - Estado de stock por producto
    """
    service = WarehouseService(db)
    return await service.get_inventory_by_location(location_id)

@router.get("/health")
async def warehouse_health():
    """Health check del módulo warehouse"""
    return {
        "service": "warehouse",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "BG001 - Procesamiento de solicitudes",
            "BG002 - Confirmación y preparación",
            "BG003 - Entrega con descuento automático",
            "BG006 - Consulta de inventario por ubicación",
            "Sistema de prioridades",
            "Vista unificada transferencias/devoluciones"
        ]
    }