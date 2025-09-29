from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime, date
from app.shared.schemas.common import BaseResponse

class ExpenseCreateRequest(BaseModel):
    concept: str = Field(..., min_length=3, max_length=255, description="Concepto del gasto")
    amount: Decimal = Field(..., gt=0, description="Monto del gasto")
    notes: Optional[str] = Field(None, max_length=500, description="Notas adicionales")
    
    @validator('concept')
    def validate_concept(cls, v):
        if not v.strip():
            raise ValueError('El concepto no puede estar vacío')
        return v.strip()


class ExpenseResponse(BaseResponse):
    expense_id: int
    concept: str
    amount: Decimal
    expense_date: datetime
    receipt_image_url: Optional[str]  
    notes: Optional[str]
    has_receipt: bool
    user_info: Dict[str, Any]
    location_info: Dict[str, Any]

class DailyExpensesResponse(BaseResponse):
    date: str
    expenses: List[Dict[str, Any]]
    summary: Dict[str, Any]
    user_info: Dict[str, Any]

class ExpenseCategory(BaseModel):
    name: str
    description: str
    suggested_concepts: List[str]

class ExpenseSummary(BaseModel):
    total_expenses: int
    total_amount: Decimal
    average_expense: Decimal
    top_concepts: List[Dict[str, Any]]
    largest_expense: Optional[Dict[str, Any]]

