# app/modules/vendor/router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import VendorService
from .schemas import VendorDashboardResponse, TransferSummaryResponse, CompletedTransfersResponse

router = APIRouter()

@router.get("/dashboard", response_model=VendorDashboardResponse)
async def get_vendor_dashboard(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Dashboard completo del vendedor con todas las métricas del día
    
    **Incluye (igual que backend antiguo):**
    - Ventas del día (confirmadas y pendientes)
    - Desglose por métodos de pago
    - Gastos del día
    - Ingreso neto calculado
    - Solicitudes de transferencia pendientes
    - Solicitudes de descuento
    - Notificaciones de devolución
    - Acciones rápidas disponibles
    """
    service = VendorService(db)
    
    # Información del usuario
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'email': current_user.email,
        'role': current_user.role,
        'location_id': current_user.location_id
    }
    
    return await service.get_dashboard(current_user.id, user_info)

@router.get("/pending-transfers", response_model=TransferSummaryResponse)
async def get_vendor_pending_transfers(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Transferencias pendientes para el vendedor (recepciones por confirmar)
    
    **Funcionalidad:**
    - Lista de productos entregados esperando confirmación
    - Priorización por urgencia (cliente vs restock)
    - Tiempo transcurrido desde entrega
    - Información del corredor
    """
    service = VendorService(db)
    return await service.get_pending_transfers(current_user.id)

@router.get("/completed-transfers", response_model=CompletedTransfersResponse)
async def get_vendor_completed_transfers(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Transferencias completadas del día (historial)
    
    **Funcionalidad:**
    - Historial de transferencias del día
    - Estadísticas de éxito
    - Duración promedio
    - Performance del vendedor
    """
    service = VendorService(db)
    return await service.get_completed_transfers(current_user.id)

@router.post("/confirm-reception/{request_id}")
async def confirm_reception(
    request_id: int,
    received_quantity: int = Query(..., description="Cantidad recibida"),
    condition_ok: bool = Query(..., description="Condición del producto OK"),
    notes: str = Query("", description="Notas de recepción"),
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE008: Confirmar recepción de transferencia con actualización automática de inventario
    
    **Funcionalidad:**
    - Confirmar recepción de producto transferido
    - Validar cantidad y condición
    - Actualizar inventario automáticamente
    - Completar el ciclo de transferencia
    """
    # Esta funcionalidad debe delegarse al módulo transfers
    # pero mantenemos el endpoint aquí por compatibilidad con frontend
    from app.modules.transfers_new.service import TransferService
    
    transfer_service = TransferService(db)
    return await transfer_service.confirm_reception(
        request_id, received_quantity, condition_ok, notes, current_user
    )

@router.get("/health")
async def vendor_health():
    """Health check del módulo vendor"""
    return {
        "service": "vendor",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "Dashboard completo del vendedor",
            "Métricas en tiempo real",
            "Transferencias pendientes",
            "Historial del día",
            "Confirmación de recepciones"
        ]
    }