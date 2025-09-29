# app/modules/classification/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Dict, Any, Optional
from app.shared.database.models import Product, ProductSize, ProductMapping

class ClassificationRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def search_products_by_reference(self, reference_code: str) -> List[Dict[str, Any]]:
        """Buscar productos por código de referencia"""
        products = self.db.query(Product).filter(
            Product.reference_code.ilike(f"%{reference_code}%")
        ).limit(10).all()
        
        return [
            {
                "id": p.id,
                "reference_code": p.reference_code,
                "brand": p.brand,
                "model": p.model,
                "color_info": p.color_info,
                "description": p.description,
                "unit_price": float(p.unit_price),
                "box_price": float(p.box_price),
                "image_url": p.image_url
            }
            for p in products
        ]
    
    def get_product_availability(self, product_id: int, user_location: str) -> Dict[str, Any]:
        """Obtener disponibilidad de producto por ubicaciones"""
        # Stock en ubicación actual
        current_stock = self.db.query(ProductSize).filter(
            and_(
                ProductSize.product_id == product_id,
                ProductSize.location_name == user_location
            )
        ).all()
        
        # Stock en otras ubicaciones
        other_stock = self.db.query(ProductSize).filter(
            and_(
                ProductSize.product_id == product_id,
                ProductSize.location_name != user_location,
                ProductSize.quantity > 0
            )
        ).all()
        
        return {
            "current_location": [
                {
                    "size": ps.size,
                    "quantity": ps.quantity,
                    "quantity_exhibition": ps.quantity_exhibition
                }
                for ps in current_stock
            ],
            "other_locations": [
                {
                    "location": ps.location_name,
                    "size": ps.size,
                    "quantity": ps.quantity
                }
                for ps in other_stock
            ]
        }
    
    def search_similar_products(self, brand: str, model: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Buscar productos similares por marca y modelo"""
        similar = self.db.query(Product).filter(
            or_(
                and_(Product.brand.ilike(f"%{brand}%"), Product.model.ilike(f"%{model}%")),
                Product.brand.ilike(f"%{brand}%")
            )
        ).limit(limit).all()
        
        return [
            {
                "reference_code": p.reference_code,
                "brand": p.brand,
                "model": p.model,
                "similarity_reason": "Misma marca" if p.brand.lower() == brand.lower() else "Marca similar"
            }
            for p in similar
        ]