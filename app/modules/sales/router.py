# app/modules/sales/router.py
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import json
from datetime import datetime

from app.config.database import get_db
from app.core.auth.dependencies import get_current_user, require_roles
from app.shared.database.models import User
from .service import SalesService
from .schemas import (
    SaleCreateRequest, SaleResponse, SaleItemResponse, 
    ExpenseCreateRequest, ExpenseResponse,
    ProductScanResponse, DailySalesResponse,
    DiscountRequestCreate, DiscountRequestResponse
)

router = APIRouter(prefix="/sales", tags=["Sales - Vendedor"])

# ==================== VE001: ESCANEO CON IA ====================

@router.post("/scan", response_model=ProductScanResponse)
async def scan_product_with_ai(
    image: UploadFile = File(..., description="Imagen del producto a escanear"),
    include_alternatives: bool = True,
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE001: Escanear productos usando reconocimiento de imágenes con IA
    
    Funcionalidades:
    - Identificación automática del producto
    - Verificación de stock en tiempo real
    - Sistema de reservas automático para clientes presentes
    - Sugerencias de productos similares disponibles
    """
    service = SalesService(db)
    
    # Validar imagen
    if not image.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Archivo debe ser una imagen")
    
    # Procesar escaneo con IA
    scan_result = await service.scan_product_with_ai(
        image_file=image,
        user_location_id=current_user.location_id,
        include_alternatives=include_alternatives
    )
    
    return scan_result

# ==================== VE002: REGISTRO DE VENTAS ====================

@router.post("/create", response_model=SaleResponse)
async def create_sale_complete(
    # Datos como Form fields para permitir archivo
    items: str = Form(..., description="JSON string con items de la venta"),
    total_amount: float = Form(..., description="Monto total de la venta", gt=0),
    payment_methods: str = Form(..., description="JSON string con métodos de pago"),
    notes: str = Form("", description="Notas adicionales"),
    requires_confirmation: bool = Form(False, description="Si requiere confirmación posterior"),
    # Archivo opcional
    receipt_image: Optional[UploadFile] = File(None, description="Comprobante de pago"),
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE002: Registrar venta completa con múltiples métodos de pago
    
    Incluye:
    - Hora de venta automática
    - Productos vendidos con detalles
    - Foto del comprobante (obligatorio para pagos no efectivo)
    - Actualización automática de inventario
    - Sistema de confirmación opcional
    """
    service = SalesService(db)
    
    try:
        # Parsear datos JSON
        items_data = json.loads(items)
        payment_methods_data = json.loads(payment_methods)
        
        # Crear request
        sale_request = SaleCreateRequest(
            items=items_data,
            total_amount=total_amount,
            payment_methods=payment_methods_data,
            notes=notes,
            requires_confirmation=requires_confirmation
        )
        
        # Procesar venta
        sale_result = await service.create_sale_complete(
            sale_data=sale_request,
            receipt_image=receipt_image,
            seller_id=current_user.id,
            location_id=current_user.location_id
        )
        
        return sale_result
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Datos JSON inválidos: {str(e)}")

@router.post("/confirm/{sale_id}")
async def confirm_sale(
    sale_id: int,
    confirmed: bool = True,
    confirmation_notes: str = "",
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Confirmar una venta pendiente de confirmación
    """
    service = SalesService(db)
    
    result = await service.confirm_sale(
        sale_id=sale_id,
        confirmed=confirmed,
        confirmation_notes=confirmation_notes,
        user_id=current_user.id
    )
    
    return result

# ==================== VE003: CONSULTA DE PRODUCTOS ====================

@router.get("/products/search")
async def search_products_by_reference(
    reference_code: str,
    include_other_locations: bool = True,
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE003: Solicitar productos de otras ubicaciones
    
    Busca productos por referencia y muestra:
    - Stock en ubicación actual
    - Stock en otras ubicaciones
    - Posibilidad de solicitar transferencia
    """
    service = SalesService(db)
    
    products = await service.search_products_by_reference(
        reference_code=reference_code,
        current_location_id=current_user.location_id,
        include_other_locations=include_other_locations
    )
    
    return {
        "success": True,
        "reference_code": reference_code,
        "products_found": products,
        "can_request_transfer": any(p["other_locations"] for p in products),
        "searched_by": {
            "user_id": current_user.id,
            "location_id": current_user.location_id
        }
    }

# ==================== VE004: GASTOS OPERATIVOS ====================

@router.post("/expenses", response_model=ExpenseResponse)
async def create_expense(
    concept: str = Form(..., description="Concepto del gasto"),
    amount: float = Form(..., description="Monto del gasto", gt=0),
    notes: str = Form("", description="Notas adicionales"),
    receipt_image: Optional[UploadFile] = File(None, description="Comprobante del gasto"),
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE004: Registrar gastos operativos
    
    Incluye:
    - Concepto y valor
    - Comprobante fotográfico opcional
    - Registro automático de fecha/hora
    """
    service = SalesService(db)
    
    expense_request = ExpenseCreateRequest(
        concept=concept,
        amount=amount,
        notes=notes
    )
    
    expense_result = await service.create_expense(
        expense_data=expense_request,
        receipt_image=receipt_image,
        user_id=current_user.id,
        location_id=current_user.location_id
    )
    
    return expense_result

@router.get("/expenses/today")
async def get_today_expenses(
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Obtener gastos del día actual
    """
    service = SalesService(db)
    
    expenses = await service.get_expenses_by_date(
        user_id=current_user.id,
        location_id=current_user.location_id,
        date=datetime.now().date()
    )
    
    return expenses

# ==================== VE005: CONSULTAR VENTAS DEL DÍA ====================

@router.get("/today", response_model=DailySalesResponse)
async def get_today_sales(
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE005: Consultar ventas realizadas en el día
    
    Incluye:
    - Ventas confirmadas y pendientes
    - Desglose por métodos de pago
    - Estadísticas del día
    """
    service = SalesService(db)
    
    daily_sales = await service.get_daily_sales(
        seller_id=current_user.id,
        location_id=current_user.location_id,
        date=datetime.now().date()
    )
    
    return daily_sales

@router.get("/pending-confirmation")
async def get_pending_confirmation_sales(
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Obtener ventas pendientes de confirmación
    """
    service = SalesService(db)
    
    pending_sales = await service.get_pending_confirmation_sales(
        seller_id=current_user.id
    )
    
    return {
        "success": True,
        "pending_sales": pending_sales,
        "count": len(pending_sales),
        "total_pending_amount": sum(sale["total_amount"] for sale in pending_sales)
    }

# ==================== VE007: SOLICITUDES DE DESCUENTO ====================

@router.post("/discount-requests", response_model=DiscountRequestResponse)
async def create_discount_request(
    discount_data: DiscountRequestCreate,
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE007: Solicitar descuentos hasta $5,000 (requiere aprobación)
    """
    service = SalesService(db)
    
    # Validar límite de descuento
    if discount_data.amount > 5000:
        raise HTTPException(
            status_code=400, 
            detail="El descuento máximo es de $5,000. Para descuentos mayores contacte al administrador."
        )
    
    discount_result = await service.create_discount_request(
        amount=discount_data.amount,
        reason=discount_data.reason,
        seller_id=current_user.id
    )
    
    return discount_result

@router.get("/discount-requests/my-requests")
async def get_my_discount_requests(
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Obtener mis solicitudes de descuento
    """
    service = SalesService(db)
    
    requests = await service.get_discount_requests_by_seller(
        seller_id=current_user.id
    )
    
    return {
        "success": True,
        "discount_requests": requests,
        "summary": {
            "total_requests": len(requests),
            "pending": len([r for r in requests if r["status"] == "pending"]),
            "approved": len([r for r in requests if r["status"] == "approved"]),
            "rejected": len([r for r in requests if r["status"] == "rejected"]),
            "total_amount_requested": sum(r["amount"] for r in requests),
            "total_amount_approved": sum(r["amount"] for r in requests if r["status"] == "approved")
        }
    }

# ==================== VE016: SISTEMA DE RESERVAS ====================

@router.post("/reserve-product")
async def reserve_product_for_client(
    reference_code: str,
    size: str,
    quantity: int = 1,
    purpose: str = "cliente",  # "cliente" o "restock"
    notes: str = "",
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    VE016: Reservar producto para cliente presente (5 min) o restock (1 min)
    """
    service = SalesService(db)
    
    if purpose not in ["cliente", "restock"]:
        raise HTTPException(status_code=400, detail="Propósito debe ser 'cliente' o 'restock'")
    
    reservation_result = await service.reserve_product(
        reference_code=reference_code,
        size=size,
        quantity=quantity,
        purpose=purpose,
        notes=notes,
        user_id=current_user.id,
        location_id=current_user.location_id
    )
    
    return reservation_result

@router.get("/my-reservations")
async def get_my_active_reservations(
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Ver mis reservas activas
    """
    service = SalesService(db)
    
    reservations = await service.get_active_reservations(
        user_id=current_user.id
    )
    
    return {
        "success": True,
        "active_reservations": reservations,
        "count": len(reservations)
    }

@router.post("/release-reservation/{reservation_id}")
async def release_product_reservation(
    reservation_id: int,
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Liberar reserva manualmente
    """
    service = SalesService(db)
    
    result = await service.release_reservation(
        reservation_id=reservation_id,
        user_id=current_user.id
    )
    
    return result

# ==================== DASHBOARD DEL VENDEDOR ====================

@router.get("/dashboard")
async def get_vendor_dashboard(
    current_user: User = Depends(require_roles(["vendedor", "administrador"])),
    db: Session = Depends(get_db)
):
    """
    Dashboard completo del vendedor con métricas del día
    """
    service = SalesService(db)
    
    dashboard_data = await service.get_vendor_dashboard(
        user_id=current_user.id,
        location_id=current_user.location_id
    )
    
    return dashboard_data

# ==================== ENDPOINTS DE UTILIDAD ====================

@router.get("/health")
async def sales_module_health():
    """
    Verificar estado del módulo de ventas
    """
    return {
        "module": "sales",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "VE001 - Escaneo con IA",
            "VE002 - Registro de ventas completo",
            "VE003 - Consulta de productos",
            "VE004 - Gastos operativos",
            "VE005 - Ventas del día",
            "VE007 - Solicitudes de descuento",
            "VE016 - Sistema de reservas",
            "Dashboard completo del vendedor"
        ]
    }