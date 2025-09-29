# app/modules/discounts/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import DiscountsService
from .schemas import DiscountRequestCreate, DiscountRequestResponse, MyDiscountRequestsResponse

router = APIRouter()

@router.post("/request", response_model=DiscountRequestResponse)
async def create_discount_request(
    discount_data: DiscountRequestCreate,
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE007: Solicitar descuentos hasta $5,000 (requiere aprobación)
    
    **Funcionalidad:**
    - Solicitar descuento con monto y razón
    - Validación automática del límite ($5,000)
    - Envío automático al administrador para aprobación
    - Sistema de seguimiento del estado
    
    **Validaciones:**
    - Monto máximo $5,000 pesos
    - Razón obligatoria (mínimo 10 caracteres)
    - Solo vendedores pueden solicitar
    
    **Estados posibles:**
    - pending: Pendiente de revisión
    - approved: Aprobado por administrador
    - rejected: Rechazado por administrador
    """
    service = DiscountsService(db)
    return await service.create_discount_request(
        discount_data=discount_data,
        seller_id=current_user.id
    )

@router.get("/my-requests", response_model=MyDiscountRequestsResponse)
async def get_my_discount_requests(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Obtener mis solicitudes de descuento
    
    **Incluye:**
    - Historial completo de solicitudes
    - Estado actual de cada solicitud
    - Información del administrador que revisó
    - Comentarios del administrador
    - Estadísticas de aprobación
    """
    service = DiscountsService(db)
    return await service.get_my_discount_requests(seller_id=current_user.id)

@router.get("/health")
async def discounts_health():
    """Health check del módulo de descuentos"""
    return {
        "service": "discounts",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "Solicitudes de descuento",
            "Validación automática de límites",
            "Sistema de aprobación",
            "Tracking de estado",
            "Estadísticas de aprobación"
        ],
        "limits": {
            "max_discount_amount": 5000,
            "currency": "COP"
        }
    }