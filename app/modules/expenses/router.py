# app/modules/expenses/router.py
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import ExpensesService
from .schemas import ExpenseCreateRequest, ExpenseResponse, DailyExpensesResponse

router = APIRouter()

@router.post("/create", response_model=ExpenseResponse)
async def create_expense(
    # Form data como en el backend antiguo
    concept: str = Form(..., description="Concepto del gasto"),
    amount: float = Form(..., description="Monto del gasto", gt=0),
    notes: str = Form("", description="Notas adicionales"),
    receipt_image: Optional[UploadFile] = File(None, description="Comprobante del gasto"),
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE004: Registrar gastos operativos del día
    
    **Igual que el backend antiguo:**
    - Form data con concept, amount, notes
    - UploadFile opcional para receipt_image
    - Subida automática a Cloudinary
    - URL almacenada en BD
    """
    service = ExpensesService(db)
    
    # Crear request validado
    expense_request = ExpenseCreateRequest(
        concept=concept,
        amount=amount,
        notes=notes
    )
    
    return await service.create_expense(
        expense_data=expense_request,
        receipt_image=receipt_image,  # UploadFile directamente
        user_id=current_user.id,
        location_id=current_user.location_id
    )

@router.get("/today", response_model=DailyExpensesResponse)
async def get_today_expenses(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    Consultar gastos realizados en el día
    
    **Incluye:**
    - Lista de gastos del día
    - Resumen por conceptos
    - Total de gastos
    - Gasto promedio
    - Gasto más grande del día
    """
    service = ExpensesService(db)
    return await service.get_daily_expenses(
        user_id=current_user.id,
        target_date=date.today()
    )

@router.get("/categories")
async def get_expense_categories(
    current_user = Depends(require_roles(["vendedor", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """Obtener categorías y conceptos sugeridos para gastos"""
    service = ExpensesService(db)
    return await service.get_expense_categories()

@router.get("/health")
async def expenses_health():
    """Health check del módulo de gastos"""
    return {
        "service": "expenses",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "Registro de gastos operativos",
            "Comprobantes digitales",
            "Categorización automática",
            "Resúmenes diarios",
            "Conceptos sugeridos"
        ]
    }