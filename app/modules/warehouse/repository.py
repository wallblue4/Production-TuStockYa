# app/modules/warehouse/repository.py
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, or_, desc, asc

from app.shared.database.models import (
    Product, ProductSize, Location, User, InventoryChange,
    TransferRequest, ReturnRequest, UserLocationAssignment,
    Sale, SaleItem
)

class WarehouseRepository:
    """
    Repositorio para todas las operaciones de datos del bodeguero
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== DEVOLUCIONES ====================
    
    def create_return(self, return_data: dict) -> ReturnRequest:
        """Crear nueva devolución"""
        db_return = ReturnRequest(**return_data)
        self.db.add(db_return)
        self.db.commit()
        self.db.refresh(db_return)
        return db_return
    
    def get_returns_by_warehouse(
        self, 
        warehouse_keeper_id: int,
        limit: int = 50
    ) -> List[ReturnRequest]:
        """Obtener devoluciones procesadas por un bodeguero"""
        return self.db.query(ReturnRequest)\
            .filter(ReturnRequest.received_by_user_id == warehouse_keeper_id)\
            .order_by(desc(ReturnRequest.received_at))\
            .limit(limit)\
            .all()
    
    # ==================== GESTIÓN DE UBICACIONES ====================
    
    def get_assigned_warehouses(self, user_id: int) -> List[Location]:
        """Obtener bodegas asignadas al bodeguero"""
        return self.db.query(Location)\
            .join(UserLocationAssignment, Location.id == UserLocationAssignment.location_id)\
            .filter(
                UserLocationAssignment.user_id == user_id,
                Location.type == 'bodega',
                Location.is_active == True
            )\
            .all()
    
    def update_product_location(
        self, 
        reference_code: str,
        size: str,
        quantity: int,
        source_location_id: int,
        destination_location_id: int,
        user_id: int,
        movement_type: str,
        reason: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Actualizar ubicación de productos entre bodegas/locales"""
        
        # 1. Verificar stock en origen
        source_product = self.db.query(Product).join(ProductSize)\
            .filter(
                Product.reference_code == reference_code,
                ProductSize.size == size,
                Product.location_id == source_location_id,
                ProductSize.quantity >= quantity
            ).first()
        
        if not source_product:
            return {"success": False, "error": "Stock insuficiente en ubicación origen"}
        
        # 2. Reducir stock en origen
        source_size = self.db.query(ProductSize)\
            .filter(
                ProductSize.product_id == source_product.id,
                ProductSize.size == size
            ).first()
        
        source_size.quantity -= quantity
        
        # 3. Aumentar stock en destino (o crear si no existe)
        dest_location = self.db.query(Location)\
            .filter(Location.id == destination_location_id).first()
        
        dest_product = self.db.query(Product)\
            .filter(
                Product.reference_code == reference_code,
                Product.location_id == destination_location_id
            ).first()
        
        if not dest_product:
            # Crear nuevo producto en destino
            dest_product = Product(
                reference_code=reference_code,
                brand=source_product.brand,
                model=source_product.model,
                color=source_product.color,
                price=source_product.price,
                location_id=destination_location_id,
                location_name=dest_location.name,
                is_active=1
            )
            self.db.add(dest_product)
            self.db.flush()
        
        # 4. Actualizar/crear talla en destino
        dest_size = self.db.query(ProductSize)\
            .filter(
                ProductSize.product_id == dest_product.id,
                ProductSize.size == size
            ).first()
        
        if dest_size:
            dest_size.quantity += quantity
        else:
            dest_size = ProductSize(
                product_id=dest_product.id,
                size=size,
                quantity=quantity,
                quantity_exhibition=0
            )
            self.db.add(dest_size)
        
        # 5. Registrar cambio de inventario
        inventory_change = InventoryChange(
            product_id=source_product.id,
            change_type=movement_type,
            size=size,
            quantity_before=source_size.quantity + quantity,
            quantity_after=source_size.quantity,
            user_id=user_id,
            notes=f"{reason} - Movido a {dest_location.name}. {notes or ''}"
        )
        self.db.add(inventory_change)
        
        self.db.commit()
        
        return {
            "success": True,
            "movement_id": inventory_change.id,
            "source_location": source_product.location.name,
            "destination_location": dest_location.name,
            "quantity_moved": quantity
        }
    
    # ==================== INVENTARIO POR UBICACIÓN ====================
    
    def get_inventory_by_locations(
        self, 
        location_ids: Optional[List[int]] = None,
        location_type: Optional[str] = None,
        reference_code: Optional[str] = None,
        brand: Optional[str] = None,
        min_stock: Optional[int] = None,
        max_stock: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Consultar inventario agrupado por ubicación"""
        
        query = self.db.query(
            Location.id.label('location_id'),
            Location.name.label('location_name'),
            Location.type.label('location_type'),
            Product.reference_code,
            Product.brand,
            Product.model,
            Product.color,
            Product.price,
            ProductSize.size,
            ProductSize.quantity,
            ProductSize.quantity_exhibition
        ).join(Product, Product.location_id == Location.id)\
         .join(ProductSize, ProductSize.product_id == Product.id)\
         .filter(
             Location.is_active == True,
             Product.is_active == 1,
             ProductSize.quantity > 0
         )
        
        # Aplicar filtros
        if location_ids:
            query = query.filter(Location.id.in_(location_ids))
        
        if location_type:
            query = query.filter(Location.type == location_type)
        
        if reference_code:
            query = query.filter(Product.reference_code.ilike(f"%{reference_code}%"))
        
        if brand:
            query = query.filter(Product.brand.ilike(f"%{brand}%"))
        
        if min_stock:
            query = query.filter(ProductSize.quantity >= min_stock)
        
        if max_stock:
            query = query.filter(ProductSize.quantity <= max_stock)
        
        results = query.order_by(
            Location.name,
            Product.brand,
            Product.model,
            ProductSize.size
        ).all()
        
        # Agrupar por ubicación
        locations_inventory = {}
        for row in results:
            location_key = row.location_id
            
            if location_key not in locations_inventory:
                locations_inventory[location_key] = {
                    "location_id": row.location_id,
                    "location_name": row.location_name,
                    "location_type": row.location_type,
                    "total_products": 0,
                    "total_units": 0,
                    "products": []
                }
            
            product_info = {
                "reference_code": row.reference_code,
                "brand": row.brand,
                "model": row.model,
                "color": row.color,
                "price": float(row.price),
                "size": row.size,
                "quantity": row.quantity,
                "quantity_exhibition": row.quantity_exhibition
            }
            
            locations_inventory[location_key]["products"].append(product_info)
            locations_inventory[location_key]["total_units"] += row.quantity
        
        # Calcular total de productos únicos por ubicación
        for location in locations_inventory.values():
            unique_references = set()
            for product in location["products"]:
                unique_references.add(product["reference_code"])
            location["total_products"] = len(unique_references)
        
        return list(locations_inventory.values())
    
    # ==================== HISTORIAL DE MOVIMIENTOS ====================
    
    def get_movement_history(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        movement_types: Optional[List[str]] = None,
        location_ids: Optional[List[int]] = None,
        reference_code: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Obtener historial de movimientos del bodeguero"""
        
        query = self.db.query(
            InventoryChange.id,
            InventoryChange.change_type,
            InventoryChange.size,
            InventoryChange.quantity_before,
            InventoryChange.quantity_after,
            InventoryChange.notes,
            InventoryChange.created_at,
            Product.reference_code,
            Product.brand,
            Product.model,
            Location.id.label('location_id'),
            Location.name.label('location_name'),
            User.first_name,
            User.last_name
        ).join(Product, Product.id == InventoryChange.product_id)\
         .join(Location, Location.id == Product.location_id)\
         .join(User, User.id == InventoryChange.user_id)\
         .filter(InventoryChange.user_id == user_id)
        
        # Aplicar filtros
        if start_date:
            query = query.filter(InventoryChange.created_at >= start_date)
        
        if end_date:
            query = query.filter(InventoryChange.created_at <= end_date)
        
        if movement_types:
            query = query.filter(InventoryChange.change_type.in_(movement_types))
        
        if location_ids:
            query = query.filter(Product.location_id.in_(location_ids))
        
        if reference_code:
            query = query.filter(Product.reference_code.ilike(f"%{reference_code}%"))
        
        results = query.order_by(desc(InventoryChange.created_at)).limit(limit).all()
        
        movements = []
        for row in results:
            quantity_change = row.quantity_after - row.quantity_before
            movements.append({
                "id": row.id,
                "movement_type": row.change_type,
                "sneaker_reference_code": row.reference_code,
                "brand": row.brand,
                "model": row.model,
                "size": row.size,
                "quantity_change": quantity_change,
                "quantity_before": row.quantity_before,
                "quantity_after": row.quantity_after,
                "location_id": row.location_id,
                "location_name": row.location_name,
                "handled_by_name": f"{row.first_name} {row.last_name}",
                "handled_at": row.created_at,
                "notes": row.notes
            })
        
        return movements
    
    # ==================== DISCREPANCIAS ====================
    
    def create_discrepancy_report(self, discrepancy_data: dict) -> Dict[str, Any]:
        """Crear reporte de discrepancia de inventario"""
        
        # Por ahora lo almacenamos en la tabla inventory_changes con un tipo especial
        discrepancy_record = InventoryChange(
            product_id=None,  # Se puede relacionar después
            change_type="discrepancy_report",
            size=discrepancy_data.get("size"),
            quantity_before=discrepancy_data.get("expected_quantity"),
            quantity_after=discrepancy_data.get("actual_quantity"),
            user_id=discrepancy_data.get("reported_by_user_id"),
            notes=f"DISCREPANCIA: {discrepancy_data.get('description')} | Tipo: {discrepancy_data.get('discrepancy_type')} | Prioridad: {discrepancy_data.get('priority')}"
        )
        
        self.db.add(discrepancy_record)
        self.db.commit()
        self.db.refresh(discrepancy_record)
        
        return {
            "id": discrepancy_record.id,
            "status": "reported",
            "reported_at": discrepancy_record.created_at
        }
    
    # ==================== DASHBOARD DEL BODEGUERO ====================
    
    def get_warehouse_dashboard_data(self, user_id: int) -> Dict[str, Any]:
        """Obtener datos del dashboard del bodeguero"""
        
        # Bodegas asignadas
        assigned_warehouses = self.get_assigned_warehouses(user_id)
        
        # Estadísticas del día
        today = date.today()
        daily_stats = {
            "transfers_processed": self.db.query(TransferRequest)\
                .filter(
                    TransferRequest.warehouse_keeper_id == user_id,
                    func.date(TransferRequest.accepted_at) == today
                ).count(),
            
            "returns_processed": self.db.query(ReturnRequest)\
                .filter(
                    ReturnRequest.received_by_user_id == user_id,
                    func.date(ReturnRequest.received_at) == today
                ).count(),
            
            "inventory_movements": self.db.query(InventoryChange)\
                .filter(
                    InventoryChange.user_id == user_id,
                    func.date(InventoryChange.created_at) == today
                ).count()
        }
        
        # Tareas pendientes
        pending_tasks = {
            "transfer_requests": self.db.query(TransferRequest)\
                .filter(
                    TransferRequest.status == 'pending',
                    TransferRequest.source_location_id.in_([w.id for w in assigned_warehouses])
                ).count(),
            
            "courier_deliveries": self.db.query(TransferRequest)\
                .filter(
                    TransferRequest.warehouse_keeper_id == user_id,
                    TransferRequest.status == 'accepted'
                ).count()
        }
        
        # Actividades recientes
        recent_activities = self.get_movement_history(user_id, limit=10)
        
        return {
            "assigned_warehouses": [
                {
                    "location_id": w.id,
                    "location_name": w.name,
                    "location_type": w.type,
                    "address": w.address,
                    "phone": w.phone,
                    "is_active": w.is_active
                } for w in assigned_warehouses
            ],
            "daily_stats": daily_stats,
            "pending_tasks": pending_tasks,
            "recent_activities": recent_activities
        }