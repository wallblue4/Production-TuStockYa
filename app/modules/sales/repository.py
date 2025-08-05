# app/modules/sales/repository.py
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, or_, desc

from app.shared.database.models import (
    Sale, SaleItem, SalePayment, Expense, Product, ProductSize,
    DiscountRequest, ProductReservation, User, Location
)

class SalesRepository:
    """
    Repositorio para todas las operaciones de datos relacionadas con ventas
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== PRODUCTOS ====================
    
    def get_product_by_reference(self, reference_code: str) -> Optional[Product]:
        """
        Obtener producto por código de referencia
        """
        return self.db.query(Product).filter(
            Product.reference_code == reference_code,
            Product.is_active == 1
        ).first()
    
    def get_product_stock_by_location(
        self, 
        reference_code: str, 
        location_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtener stock de producto en una ubicación específica
        """
        # Obtener nombre de la ubicación
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return []
        
        # Buscar productos y sus tallas
        results = self.db.query(Product, ProductSize).join(
            ProductSize, Product.id == ProductSize.product_id
        ).filter(
            Product.reference_code == reference_code,
            Product.location_name == location.name,
            Product.is_active == 1,
            ProductSize.quantity > 0
        ).all()
        
        stock_info = []
        for product, size in results:
            stock_info.append({
                "size": size.size,
                "quantity_stock": size.quantity,
                "quantity_exhibition": size.quantity_exhibition,
                "location_id": location_id,
                "location_name": location.name
            })
        
        return stock_info
    
    def get_product_stock_other_locations(
        self, 
        reference_code: str, 
        exclude_location_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtener stock de producto en otras ubicaciones
        """
        # Obtener ubicación a excluir
        exclude_location = self.db.query(Location).filter(
            Location.id == exclude_location_id
        ).first()
        exclude_location_name = exclude_location.name if exclude_location else ""
        
        # Buscar en otras ubicaciones
        results = self.db.query(Product, ProductSize, Location).join(
            ProductSize, Product.id == ProductSize.product_id
        ).join(
            Location, Product.location_name == Location.name
        ).filter(
            Product.reference_code == reference_code,
            Product.location_name != exclude_location_name,
            Product.is_active == 1,
            ProductSize.quantity > 0
        ).all()
        
        other_stock = []
        for product, size, location in results:
            other_stock.append({
                "size": size.size,
                "quantity_stock": size.quantity,
                "quantity_exhibition": size.quantity_exhibition,
                "location_id": location.id,
                "location_name": location.name,
                "location_type": location.type,
                "location_address": location.address
            })
        
        return other_stock
    
    def get_total_stock_by_location(
        self, 
        reference_code: str, 
        location_id: int
    ) -> int:
        """
        Obtener stock total de un producto en una ubicación
        """
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return 0
        
        total_stock = self.db.query(func.sum(ProductSize.quantity)).join(
            Product, ProductSize.product_id == Product.id
        ).filter(
            Product.reference_code == reference_code,
            Product.location_name == location.name,
            Product.is_active == 1
        ).scalar()
        
        return total_stock or 0
    
    def find_similar_products(
        self, 
        brand: str, 
        model: str, 
        exclude_reference: str, 
        location_id: int, 
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Encontrar productos similares disponibles
        """
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return []
        
        # Buscar productos similares por marca o modelo
        results = self.db.query(Product, ProductSize).join(
            ProductSize, Product.id == ProductSize.product_id
        ).filter(
            or_(
                Product.brand.ilike(f'%{brand}%'),
                Product.model.ilike(f'%{model}%')
            ),
            Product.reference_code != exclude_reference,
            Product.location_name == location.name,
            Product.is_active == 1,
            ProductSize.quantity > 0
        ).limit(limit).all()
        
        similar_products = []
        for product, size in results:
            similar_products.append({
                "reference_code": product.reference_code,
                "brand": product.brand,
                "model": product.model,
                "size": size.size,
                "available_quantity": size.quantity,
                "unit_price": float(product.unit_price),
                "location": location.name,
                "similarity_reason": "Misma marca" if product.brand == brand else "Modelo similar"
            })
        
        return similar_products
    
    def get_product_in_other_locations(
        self, 
        reference_code: str, 
        exclude_location_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtener producto disponible en otras ubicaciones
        """
        exclude_location = self.db.query(Location).filter(
            Location.id == exclude_location_id
        ).first()
        exclude_location_name = exclude_location.name if exclude_location else ""
        
        # Agrupar por ubicación
        locations_map = {}
        
        results = self.db.query(Product, ProductSize, Location).join(
            ProductSize, Product.id == ProductSize.product_id
        ).join(
            Location, Product.location_name == Location.name
        ).filter(
            Product.reference_code == reference_code,
            Product.location_name != exclude_location_name,
            Product.is_active == 1,
            ProductSize.quantity > 0
        ).all()
        
        for product, size, location in results:
            if location.id not in locations_map:
                locations_map[location.id] = {
                    "reference_code": product.reference_code,
                    "brand": product.brand,
                    "model": product.model,
                    "description": product.description,
                    "color": product.color_info,
                    "unit_price": float(product.unit_price),
                    "box_price": float(product.box_price),
                    "image_url": product.image_url,
                    "current_location_stock": [],
                    "other_locations_stock": [{
                        "size": size.size,
                        "quantity_stock": size.quantity,
                        "quantity_exhibition": size.quantity_exhibition,
                        "location_id": location.id,
                        "location_name": location.name,
                        "location_type": location.type
                    }],
                    "can_request_transfer": True,
                    "estimated_transfer_time": "2-4 horas"
                }
            else:
                locations_map[location.id]["other_locations_stock"].append({
                    "size": size.size,
                    "quantity_stock": size.quantity,
                    "quantity_exhibition": size.quantity_exhibition,
                    "location_id": location.id,
                    "location_name": location.name,
                    "location_type": location.type
                })
        
        return list(locations_map.values())
    
    def decrease_product_stock(
        self, 
        reference_code: str, 
        size: str, 
        quantity: int, 
        location_id: int
    ):
        """
        Decrementar stock de producto después de venta
        """
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return
        
        # Buscar el producto y la talla específica
        product_size = self.db.query(ProductSize).join(
            Product, ProductSize.product_id == Product.id
        ).filter(
            Product.reference_code == reference_code,
            Product.location_name == location.name,
            ProductSize.size == size
        ).first()
        
        if product_size and product_size.quantity >= quantity:
            product_size.quantity -= quantity
            self.db.commit()
    
    # ==================== RESERVAS ====================
    
    def get_reserved_quantity(
        self, 
        reference_code: str, 
        location_id: int
    ) -> int:
        """
        Obtener cantidad total reservada de un producto
        """
        reserved_qty = self.db.query(func.sum(ProductReservation.quantity)).filter(
            ProductReservation.sneaker_reference_code == reference_code,
            ProductReservation.location_id == location_id,
            ProductReservation.status == 'active',
            ProductReservation.expires_at > datetime.now()
        ).scalar()
        
        return reserved_qty or 0
    
    def create_product_reservation(
        self,
        reference_code: str,
        size: str,
        quantity: int,
        user_id: int,
        location_id: int,
        purpose: str,
        expires_at: datetime
    ) -> ProductReservation:
        """
        Crear reserva de producto
        """
        reservation = ProductReservation(
            sneaker_reference_code=reference_code,
            size=size,
            quantity=quantity,
            user_id=user_id,
            location_id=location_id,
            purpose=purpose,
            status='active',
            reserved_at=datetime.now(),
            expires_at=expires_at
        )
        
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        
        return reservation
    
    def get_active_reservations(self, user_id: int) -> List[ProductReservation]:
        """
        Obtener reservas activas de un usuario
        """
        return self.db.query(ProductReservation).filter(
            ProductReservation.user_id == user_id,
            ProductReservation.status == 'active',
            ProductReservation.expires_at > datetime.now()
        ).order_by(desc(ProductReservation.reserved_at)).all()
    
    def get_reservation_by_id(self, reservation_id: int) -> Optional[ProductReservation]:
        """
        Obtener reserva por ID
        """
        return self.db.query(ProductReservation).filter(
            ProductReservation.id == reservation_id
        ).first()
    
    def release_reservation(self, reservation_id: int):
        """
        Liberar reserva manualmente
        """
        reservation = self.get_reservation_by_id(reservation_id)
        if reservation:
            reservation.status = 'released'
            reservation.released_at = datetime.now()
            self.db.commit()
    
    # ==================== VENTAS ====================
    
    def create_sale(
        self,
        seller_id: int,
        location_id: int,
        total_amount: float,
        receipt_image: Optional[str],
        notes: str,
        requires_confirmation: bool
    ) -> Sale:
        """
        Crear nueva venta
        """
        sale = Sale(
            seller_id=seller_id,
            location_id=location_id,
            total_amount=total_amount,
            receipt_image=receipt_image,
            sale_date=datetime.now(),
            status='completed',
            notes=notes,
            requires_confirmation=requires_confirmation,
            confirmed=not requires_confirmation,
            confirmed_at=None if requires_confirmation else datetime.now()
        )
        
        self.db.add(sale)
        self.db.commit()
        self.db.refresh(sale)
        
        return sale
    
    def create_sale_item(self, sale_id: int, item_data: Any) -> SaleItem:
        """
        Crear item de venta
        """
        subtotal = item_data.quantity * item_data.unit_price
        
        sale_item = SaleItem(
            sale_id=sale_id,
            sneaker_reference_code=item_data.sneaker_reference_code,
            brand=item_data.brand,
            model=item_data.model,
            color=item_data.color,
            size=item_data.size,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            subtotal=subtotal
        )
        
        self.db.add(sale_item)
        self.db.commit()
        self.db.refresh(sale_item)
        
        return sale_item
    
    def create_sale_payment(self, sale_id: int, payment_data: Any) -> SalePayment:
        """
        Crear método de pago de venta
        """
        sale_payment = SalePayment(
            sale_id=sale_id,
            payment_type=payment_data.type,
            amount=payment_data.amount,
            reference=payment_data.reference,
            created_at=datetime.now()
        )
        
        self.db.add(sale_payment)
        self.db.commit()
        self.db.refresh(sale_payment)
        
        return sale_payment
    
    def get_sale_by_id(self, sale_id: int) -> Optional[Sale]:
        """
        Obtener venta por ID
        """
        return self.db.query(Sale).filter(Sale.id == sale_id).first()
    
    def get_sale_items(self, sale_id: int) -> List[SaleItem]:
        """
        Obtener items de una venta
        """
        return self.db.query(SaleItem).filter(SaleItem.sale_id == sale_id).all()
    
    def get_sale_payments(self, sale_id: int) -> List[SalePayment]:
        """
        Obtener métodos de pago de una venta
        """
        return self.db.query(SalePayment).filter(SalePayment.sale_id == sale_id).all()
    
    def confirm_sale(
        self, 
        sale_id: int, 
        confirmed: bool, 
        confirmation_notes: str
    ) -> Sale:
        """
        Confirmar o rechazar venta
        """
        sale = self.get_sale_by_id(sale_id)
        if sale:
            sale.confirmed = confirmed
            sale.confirmed_at = datetime.now() if confirmed else None
            if confirmation_notes:
                sale.notes = (sale.notes or "") + f"\nConfirmación: {confirmation_notes}"
            
            self.db.commit()
            self.db.refresh(sale)
        
        return sale
    
    def get_sales_by_seller_and_date(
        self, 
        seller_id: int, 
        location_id: int, 
        date_filter: date
    ) -> List[Sale]:
        """
        Obtener ventas de un vendedor por fecha
        """
        return self.db.query(Sale).filter(
            Sale.seller_id == seller_id,
            Sale.location_id == location_id,
            func.date(Sale.sale_date) == date_filter
        ).order_by(desc(Sale.sale_date)).all()
    
    def get_pending_confirmation_sales(self, seller_id: int) -> List[Sale]:
        """
        Obtener ventas pendientes de confirmación
        """
        return self.db.query(Sale).filter(
            Sale.seller_id == seller_id,
            Sale.requires_confirmation == True,
            Sale.confirmed == False
        ).order_by(desc(Sale.sale_date)).all()
    
    # ==================== GASTOS ====================
    
    def create_expense(
        self,
        user_id: int,
        location_id: int,
        concept: str,
        amount: float,
        receipt_image: Optional[str],
        notes: str
    ) -> Expense:
        """
        Crear nuevo gasto
        """
        expense = Expense(
            user_id=user_id,
            location_id=location_id,
            concept=concept,
            amount=amount,
            receipt_image=receipt_image,
            expense_date=datetime.now(),
            notes=notes
        )
        
        self.db.add(expense)
        self.db.commit()
        self.db.refresh(expense)
        
        return expense
    
    def get_expenses_by_user_and_date(
        self, 
        user_id: int, 
        location_id: int, 
        date_filter: date
    ) -> List[Expense]:
        """
        Obtener gastos de un usuario por fecha
        """
        return self.db.query(Expense).filter(
            Expense.user_id == user_id,
            Expense.location_id == location_id,
            func.date(Expense.expense_date) == date_filter
        ).order_by(desc(Expense.expense_date)).all()
    
    # ==================== SOLICITUDES DE DESCUENTO ====================
    
    def create_discount_request(
        self,
        seller_id: int,
        amount: float,
        reason: str
    ) -> DiscountRequest:
        """
        Crear solicitud de descuento
        """
        discount_request = DiscountRequest(
            seller_id=seller_id,
            amount=amount,
            reason=reason,
            status='pending',
            requested_at=datetime.now()
        )
        
        self.db.add(discount_request)
        self.db.commit()
        self.db.refresh(discount_request)
        
        return discount_request
    
    def get_discount_requests_by_seller(self, seller_id: int) -> List[DiscountRequest]:
        """
        Obtener solicitudes de descuento de un vendedor
        """
        return self.db.query(DiscountRequest).filter(
            DiscountRequest.seller_id == seller_id
        ).order_by(desc(DiscountRequest.requested_at)).all()
    
    def get_pending_discount_requests(self, seller_id: int) -> List[DiscountRequest]:
        """
        Obtener solicitudes de descuento pendientes
        """
        return self.db.query(DiscountRequest).filter(
            DiscountRequest.seller_id == seller_id,
            DiscountRequest.status == 'pending'
        ).all()
    
    # ==================== UTILIDADES ====================
    
    def cleanup_expired_reservations(self) -> int:
        """
        Limpiar reservas expiradas automáticamente
        """
        expired_count = self.db.query(ProductReservation).filter(
            ProductReservation.status == 'active',
            ProductReservation.expires_at <= datetime.now()
        ).count()
        
        # Marcar como expiradas
        self.db.query(ProductReservation).filter(
            ProductReservation.status == 'active',
            ProductReservation.expires_at <= datetime.now()
        ).update({
            ProductReservation.status: 'expired',
            ProductReservation.released_at: datetime.now()
        })
        
        self.db.commit()
        return expired_count
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Obtener usuario por ID
        """
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_location_by_id(self, location_id: int) -> Optional[Location]:
        """
        Obtener ubicación por ID
        """
        return self.db.query(Location).filter(Location.id == location_id).first()