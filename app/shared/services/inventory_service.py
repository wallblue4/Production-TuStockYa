# app/shared/services/inventory_service.py
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.shared.database.models import Product, ProductSize, InventoryChange

class InventoryService:
    """Servicio compartido para operaciones de inventario"""
    
    @staticmethod
    def update_stock_after_sale(db: Session, items: List[Dict[str, Any]], user_id: int, location_name: str) -> bool:
        """Actualizar inventario después de venta"""
        try:
            for item in items:
                # Buscar product_size específico
                product_size = db.query(ProductSize).join(Product).filter(
                    and_(
                        Product.reference_code == item['sneaker_reference_code'],
                        ProductSize.size == item['size'],
                        ProductSize.location_name == location_name
                    )
                ).first()
                
                if not product_size or product_size.quantity < item['quantity']:
                    db.rollback()
                    return False
                
                # Actualizar cantidad
                quantity_before = product_size.quantity
                product_size.quantity -= item['quantity']
                
                # Registrar cambio en historial
                inventory_change = InventoryChange(
                    product_id=product_size.product_id,
                    change_type='sale',
                    size=item['size'],
                    quantity_before=quantity_before,
                    quantity_after=product_size.quantity,
                    user_id=user_id,
                    notes=f"Venta - Reducción de stock"
                )
                db.add(inventory_change)
            
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            print(f"Error updating inventory: {e}")
            return False
    
    @staticmethod
    def check_product_availability(db: Session, reference_code: str, size: str, location_name: str) -> Dict[str, Any]:
        """Verificar disponibilidad de producto"""
        product_size = db.query(ProductSize).join(Product).filter(
            and_(
                Product.reference_code == reference_code,
                ProductSize.size == size,
                ProductSize.location_name == location_name
            )
        ).first()
        
        if not product_size:
            return {"available": False, "quantity": 0, "can_sell": False}
        
        return {
            "available": product_size.quantity > 0,
            "quantity": product_size.quantity,
            "can_sell": product_size.quantity > 0
        }