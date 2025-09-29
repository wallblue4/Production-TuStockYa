# app/modules/sales_new/router.py
import json
from typing import Optional
from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import SalesService
from .schemas import (
    SaleCreateRequest, SaleResponse, SaleConfirmationRequest,
    DailySalesResponse, PendingSalesResponse
)

router = APIRouter()

@router.post("/create", response_model=SaleResponse)
async def create_sale_complete(
    # Form data para permitir archivo
    items: str = Form(..., description="JSON string con items de la venta"),
    total_amount: float = Form(..., description="Monto total de la venta", gt=0),
    payment_methods: str = Form(..., description="JSON string con métodos de pago"),
    notes: str = Form("", description="Notas adicionales"),
    requires_confirmation: bool = Form(False, description="Requiere confirmación posterior"),
    receipt_image: Optional[UploadFile] = File(None, description="Comprobante de pago"),
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE002: Registrar venta completa con múltiples métodos de pago
    
    **Incluye:**
    - Registro de venta con fecha automática
    - Productos vendidos con detalles completos
    - Múltiples métodos de pago
    - Comprobante opcional
    - Actualización automática de inventario
    - Sistema de confirmación opcional
    """
    service = SalesService(db)
    
    try:
        # Parsear datos JSON
        items_data = json.loads(items)
        payment_methods_data = json.loads(payment_methods)
        
        # Crear request validado
        sale_request = SaleCreateRequest(
            items=items_data,
            total_amount=total_amount,
            payment_methods=payment_methods_data,
            notes=notes,
            requires_confirmation=requires_confirmation
        )
        
        # Procesar venta
        return await service.create_sale_complete(
            sale_data=sale_request,
            receipt_image=receipt_image,
            seller_id=current_user.id,
            location_id=current_user.location_id
        )
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Datos JSON inválidos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando venta: {str(e)}")

@router.get("/today", response_model=DailySalesResponse)
async def get_today_sales(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE005: Consultar ventas realizadas en el día
    
    **Incluye:**
    - Ventas confirmadas y pendientes
    - Desglose por métodos de pago
    - Estadísticas del día
    - Resumen financiero
    """
    service = SalesService(db)
    return await service.get_daily_sales(
        seller_id=current_user.id,
        target_date=date.today()
    )

@router.get("/pending-confirmation", response_model=PendingSalesResponse)
async def get_pending_confirmation_sales(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """Obtener ventas pendientes de confirmación"""
    service = SalesService(db)
    return await service.get_pending_confirmation_sales(current_user.id)

@router.post("/confirm")
async def confirm_sale(
    confirmation: SaleConfirmationRequest,
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """Confirmar o rechazar una venta pendiente"""
    service = SalesService(db)
    return await service.confirm_sale(
        sale_id=confirmation.sale_id,
        confirmed=confirmation.confirmed,
        confirmation_notes=confirmation.confirmation_notes or "",
        user_id=current_user.id
    )

@router.get("/health")
async def sales_health():
    """Health check del módulo de ventas"""
    return {
        "service": "sales",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "Registro de ventas completo",
            "Múltiples métodos de pago",
            "Actualización automática de inventario",
            "Sistema de confirmación",
            "Comprobantes digitales"
        ]
    }