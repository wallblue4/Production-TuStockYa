# app/modules/expenses/service.py
from typing import Dict, Any, Optional
from datetime import date, datetime
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .repository import ExpensesRepository
from .schemas import ExpenseCreateRequest, ExpenseResponse, DailyExpensesResponse
from app.shared.services.cloudinary_service import CloudinaryService


class ExpensesService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ExpensesRepository(db)
        self.cloudinary = CloudinaryService()
    
    async def create_expense(
        self,
        expense_data: ExpenseCreateRequest,
        receipt_image: Optional[UploadFile],  # UploadFile directamente
        user_id: int,
        location_id: int
    ) -> ExpenseResponse:
        """Crear nuevo gasto operativo"""
        
        try:
            # Subir imagen a Cloudinary si existe
            receipt_url = None
            if receipt_image and receipt_image.filename:
                try:
                    receipt_url = await self.cloudinary.upload_receipt_image(
                        receipt_image, "expense", user_id
                    )
                except Exception as e:
                    # Log error pero no fallar por imagen
                    print(f"Error subiendo comprobante: {e}")
                    receipt_url = None
            
            # Crear gasto en BD
            expense_dict = expense_data.dict()
            expense_dict['receipt_image'] = receipt_url  # URL de Cloudinary
            
            expense = self.repository.create_expense(expense_dict, user_id, location_id)
            
            return ExpenseResponse(
                success=True,
                message="Gasto registrado exitosamente",
                expense_id=expense.id,
                concept=expense.concept,
                amount=expense.amount,
                expense_date=expense.expense_date,
                receipt_image_url=receipt_url,  # URL de Cloudinary
                notes=expense.notes,
                has_receipt=receipt_url is not None,
                user_info={
                    "user_id": user_id,
                    "location_id": location_id
                },
                location_info={
                    "location_id": location_id,
                    "location_name": f"Local #{location_id}"
                }
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error registrando gasto: {str(e)}")
    
    async def get_daily_expenses(self, user_id: int, target_date: date) -> DailyExpensesResponse:
        """Obtener gastos del día"""
        expenses = self.repository.get_expenses_by_user_and_date(user_id, target_date)
        summary = self.repository.get_daily_expenses_summary(user_id, target_date)
        
        expenses_data = []
        for expense in expenses:
            expenses_data.append({
                "id": expense.id,
                "concept": expense.concept,
                "amount": float(expense.amount),
                "expense_date": expense.expense_date.isoformat(),
                "has_receipt": expense.receipt_image is not None,
                "notes": expense.notes
            })
        
        return DailyExpensesResponse(
            success=True,
            message=f"Gastos del {target_date}",
            date=target_date.isoformat(),
            expenses=expenses_data,
            summary=summary,
            user_info={"user_id": user_id}
        )
    
    async def get_expense_categories(self) -> Dict[str, Any]:
        """Obtener categorías y conceptos sugeridos"""
        categories = self.repository.get_expense_categories()
        
        return {
            "success": True,
            "categories": categories,
            "total_categories": len(categories),
            "message": "Categorías de gastos disponibles"
        }
    
    # async def _save_receipt_image(self, image_base64: str, user_id: int) -> str:
    #     """Guardar imagen de recibo desde base64"""
    #     try:
    #         # Decodificar base64
    #         image_data = base64.b64decode(image_base64)
            
    #         # Crear directorio si no existe
    #         receipts_dir = "storage/receipts"
    #         os.makedirs(receipts_dir, exist_ok=True)
            
    #         # Generar nombre único
    #         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #         filename = f"expense_{user_id}_{timestamp}.jpg"
    #         file_path = os.path.join(receipts_dir, filename)
            
    #         # Guardar archivo
    #         with open(file_path, "wb") as f:
    #             f.write(image_data)
            
    #         return file_path
            
    #     except Exception as e:
    #         print(f"Error saving receipt image: {e}")
    #         return None