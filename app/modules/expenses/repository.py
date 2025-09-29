# app/modules/expenses/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import List, Dict, Any
from datetime import date, datetime
from decimal import Decimal

from app.shared.database.models import Expense, User, Location

class ExpensesRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create_expense(self, expense_data: Dict[str, Any], user_id: int, location_id: int) -> Expense:
        """Crear nuevo gasto"""
        expense = Expense(
            user_id=user_id,
            location_id=location_id,
            concept=expense_data['concept'],
            amount=expense_data['amount'],
            receipt_image=expense_data.get('receipt_image'),
            notes=expense_data.get('notes'),
            expense_date=datetime.now()
        )
        
        self.db.add(expense)
        self.db.commit()
        self.db.refresh(expense)
        return expense
    
    def get_expenses_by_user_and_date(self, user_id: int, target_date: date) -> List[Expense]:
        """Obtener gastos por usuario y fecha"""
        return self.db.query(Expense).filter(
            and_(
                Expense.user_id == user_id,
                func.date(Expense.expense_date) == target_date
            )
        ).order_by(Expense.expense_date.desc()).all()
    
    def get_expenses_by_location_and_date(self, location_id: int, target_date: date) -> List[Expense]:
        """Obtener gastos por ubicación y fecha"""
        return self.db.query(Expense).filter(
            and_(
                Expense.location_id == location_id,
                func.date(Expense.expense_date) == target_date
            )
        ).order_by(Expense.expense_date.desc()).all()
    
    def get_daily_expenses_summary(self, user_id: int, target_date: date) -> Dict[str, Any]:
        """Obtener resumen de gastos del día"""
        expenses = self.get_expenses_by_user_and_date(user_id, target_date)
        
        if not expenses:
            return {
                "total_expenses": 0,
                "total_amount": 0.0,
                "average_expense": 0.0,
                "top_concepts": [],
                "largest_expense": None,
                "most_common_concept": None
            }
        
        total_amount = sum(e.amount for e in expenses)
        average_expense = total_amount / len(expenses)
        
        # Agrupar por concepto
        concept_totals = {}
        for expense in expenses:
            concept = expense.concept
            if concept in concept_totals:
                concept_totals[concept]['amount'] += expense.amount
                concept_totals[concept]['count'] += 1
            else:
                concept_totals[concept] = {
                    'amount': expense.amount,
                    'count': 1
                }
        
        # Top conceptos por monto
        top_concepts = sorted(
            [
                {
                    'concept': concept,
                    'total_amount': float(data['amount']),
                    'count': data['count']
                }
                for concept, data in concept_totals.items()
            ],
            key=lambda x: x['total_amount'],
            reverse=True
        )[:5]
        
        # Gasto más grande
        largest_expense = max(expenses, key=lambda x: x.amount)
        
        return {
            "total_expenses": len(expenses),
            "total_amount": float(total_amount),
            "average_expense": float(average_expense),
            "top_concepts": top_concepts,
            "largest_expense": {
                "id": largest_expense.id,
                "concept": largest_expense.concept,
                "amount": float(largest_expense.amount),
                "expense_date": largest_expense.expense_date.isoformat()
            },
            "most_common_concept": top_concepts[0]['concept'] if top_concepts else None
        }
    
    def get_expense_categories(self) -> List[Dict[str, Any]]:
        """Obtener categorías de gastos sugeridas"""
        return [
            {
                "name": "Transporte",
                "description": "Gastos de movilización",
                "suggested_concepts": ["Taxi", "Uber", "Gasolina", "Parqueadero", "Bus"]
            },
            {
                "name": "Alimentación",
                "description": "Gastos de comida y bebidas",
                "suggested_concepts": ["Almuerzo", "Desayuno", "Cena", "Café", "Snacks"]
            },
            {
                "name": "Materiales",
                "description": "Insumos y materiales de trabajo",
                "suggested_concepts": ["Bolsas", "Etiquetas", "Limpieza", "Papelería"]
            },
            {
                "name": "Servicios",
                "description": "Servicios diversos",
                "suggested_concepts": ["Internet", "Teléfono", "Servicios públicos", "Mantenimiento"]
            },
            {
                "name": "Otros",
                "description": "Gastos varios",
                "suggested_concepts": ["Varios", "Emergencia", "Imprevisto"]
            }
        ]