# app/modules/transfers_new/router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import TransfersService
from .schemas import TransferRequestCreate, TransferRequestResponse, MyTransferRequestsResponse

router = APIRouter()

@router.post("/request", response_model=TransferRequestResponse)
async def create_transfer_request(
    transfer_data: TransferRequestCreate,
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE003: Solicitar productos de otras ubicaciones
    
    **Funcionalidad:**
    - Crear solicitud especificando producto, cantidad y urgencia
    - Validar disponibilidad antes de crear solicitud
    - Establecer prioridad según propósito (cliente vs restock)
    - Sistema de reservas automático para clientes presentes
    
    **Casos de uso:**
    - Cliente esperando producto que no está en local
    - Solicitar productos para restock de exhibición
    - Transferencia entre bodegas
    """
    service = TransfersService(db)
    return await service.create_transfer_request(transfer_data, current_user.id)

@router.get("/my-requests", response_model=MyTransferRequestsResponse)
async def get_my_transfer_requests(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener mis solicitudes de transferencia
    
    **Vista unificada:**
    - Transferencias y devoluciones en una sola lista
    - Estado detallado con progreso
    - Información completa de participantes
    - Tiempo transcurrido y próximos pasos
    """
    service = TransfersService(db)
    
    user_info = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name
    }
    
    return await service.get_my_transfer_requests(current_user.id, user_info)

@router.get("/health")
async def transfers_health():
    """Health check del módulo de transferencias"""
    return {
        "service": "transfers",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "VE003 - Solicitud de productos",
            "VE008 - Confirmación de recepción",
            "Sistema de prioridades",
            "Actualización automática de inventario",
            "Tracking completo de estado"
        ]
    }