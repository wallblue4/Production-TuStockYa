# app/modules/sales_new/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import List, Dict, Any
from datetime import date, datetime
from decimal import Decimal

from app.shared.database.models import Sale, SaleItem, SalePayment, User

class SalesRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create_sale(self, sale_data: Dict[str, Any], seller_id: int, location_id: int) -> Sale:
        """Crear nueva venta en la base de datos"""
        sale = Sale(
            seller_id=seller_id,
            location_id=location_id,
            total_amount=sale_data['total_amount'],
            notes=sale_data.get('notes'),
            requires_confirmation=sale_data.get('requires_confirmation', False),
            confirmed=not sale_data.get('requires_confirmation', False),
            status='completed' if not sale_data.get('requires_confirmation', False) else 'pending_confirmation'
        )
        
        self.db.add(sale)
        self.db.flush()  # Para obtener el ID
        
        # Agregar items
        for item_data in sale_data['items']:
            sale_item = SaleItem(
                sale_id=sale.id,
                sneaker_reference_code=item_data['sneaker_reference_code'],
                brand=item_data['brand'],
                model=item_data['model'],
                color=item_data.get('color'),
                size=item_data['size'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                subtotal=item_data['quantity'] * item_data['unit_price']
            )
            self.db.add(sale_item)
        
        # Agregar métodos de pago
        for payment_data in sale_data['payment_methods']:
            sale_payment = SalePayment(
                sale_id=sale.id,
                payment_type=payment_data['type'],
                amount=payment_data['amount'],
                reference=payment_data.get('reference')
            )
            self.db.add(sale_payment)
        
        self.db.commit()
        self.db.refresh(sale)
        return sale
    
    def get_sales_by_seller_and_date(self, seller_id: int, target_date: date) -> List[Sale]:
        """Obtener ventas por vendedor y fecha"""
        return self.db.query(Sale).filter(
            and_(
                Sale.seller_id == seller_id,
                func.date(Sale.sale_date) == target_date
            )
        ).all()
    
    def get_pending_confirmation_sales(self, seller_id: int) -> List[Sale]:
        """Obtener ventas pendientes de confirmación"""
        return self.db.query(Sale).filter(
            and_(
                Sale.seller_id == seller_id,
                Sale.requires_confirmation == True,
                Sale.confirmed == False
            )
        ).all()
    
    def confirm_sale(self, sale_id: int, confirmed: bool, notes: str, user_id: int) -> bool:
        """Confirmar o rechazar una venta"""
        sale = self.db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            return False
        
        sale.confirmed = confirmed
        sale.confirmed_at = datetime.now()
        sale.status = 'completed' if confirmed else 'cancelled'
        if notes:
            sale.notes = f"{sale.notes}\nConfirmación: {notes}" if sale.notes else f"Confirmación: {notes}"
        
        self.db.commit()
        return True
    
    def get_sale_items(self, sale_id: int) -> List[SaleItem]:
        """Obtener items de una venta"""
        return self.db.query(SaleItem).filter(SaleItem.sale_id == sale_id).all()
    
    def get_daily_sales_summary(self, seller_id: int, target_date: date) -> Dict[str, Any]:
        """Obtener resumen de ventas del día"""
        sales = self.get_sales_by_seller_and_date(seller_id, target_date)
        
        total_sales = len(sales)
        confirmed_sales = len([s for s in sales if s.confirmed])
        pending_sales = len([s for s in sales if s.requires_confirmation and not s.confirmed])
        
        total_amount = sum(s.total_amount for s in sales if s.confirmed)
        pending_amount = sum(s.total_amount for s in sales if s.requires_confirmation and not s.confirmed)
        
        return {
            "total_sales": total_sales,
            "confirmed_sales": confirmed_sales,
            "pending_sales": pending_sales,
            "total_amount": float(total_amount),
            "pending_amount": float(pending_amount),
            "confirmed_amount": float(total_amount),
            "average_sale": float(total_amount / confirmed_sales) if confirmed_sales > 0 else 0
        }