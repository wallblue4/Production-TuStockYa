# app/modules/admin/repository.py
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, or_, desc, asc
from decimal import Decimal

from app.shared.database.models import (
    User, Location, Sale, SaleItem, Product, ProductSize,
    DiscountRequest, TransferRequest, Expense, UserLocationAssignment,
    InventoryChange , AdminLocationAssignment
)

class AdminRepository:
    """
    Repositorio para todas las operaciones de datos del administrador
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== GESTIÓN DE USUARIOS ====================
    
    def create_user(self, user_data: dict) -> User:
        """Crear nuevo usuario"""
        # Hashear password (en producción usar bcrypt)
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        hashed_password = pwd_context.hash(user_data["password"])
        user_data["password_hash"] = hashed_password 
        del user_data["password"]
        
        db_user = User(**user_data)
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user
    
    
    def update_user(self, user_id: int, update_data: dict) -> Optional[User]:
        """Actualizar usuario"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if user:
            for key, value in update_data.items():
                if hasattr(user, key) and value is not None:
                    setattr(user, key, value)
            self.db.commit()
            self.db.refresh(user)
        return user

    def create_admin_assignment(self, assignment_data: dict) -> AdminLocationAssignment:
        """Crear asignación de administrador a ubicación"""
        
        # Verificar si ya existe la asignación
        existing = self.db.query(AdminLocationAssignment)\
            .filter(
                AdminLocationAssignment.admin_id == assignment_data["admin_id"],
                AdminLocationAssignment.location_id == assignment_data["location_id"]
            ).first()
        
        if existing:
            # Reactivar si existe pero está inactiva
            existing.is_active = True
            existing.assigned_at = func.current_timestamp()
            existing.assigned_by_user_id = assignment_data.get("assigned_by_user_id")
            existing.notes = assignment_data.get("notes")
            self.db.commit()
            self.db.refresh(existing)
            return existing
        
        # Crear nueva asignación
        assignment = AdminLocationAssignment(**assignment_data)
        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment
    
    def get_admin_assignments(self, admin_id: int) -> List[AdminLocationAssignment]:
        """Obtener asignaciones de un administrador"""
        return self.db.query(AdminLocationAssignment)\
            .filter(
                AdminLocationAssignment.admin_id == admin_id,
                AdminLocationAssignment.is_active == True
            )\
            .join(Location, AdminLocationAssignment.location_id == Location.id)\
            .filter(Location.is_active == True)\
            .all()
    
    def remove_admin_assignment(self, admin_id: int, location_id: int) -> bool:
        """Remover asignación de administrador"""
        assignment = self.db.query(AdminLocationAssignment)\
            .filter(
                AdminLocationAssignment.admin_id == admin_id,
                AdminLocationAssignment.location_id == location_id
            ).first()
        
        if assignment:
            assignment.is_active = False
            self.db.commit()
            return True
        return False
    
    # ==================== MÉTODOS CORREGIDOS ====================
    
    def get_managed_locations(self, admin_id: int) -> List[Location]:
        """Obtener ubicaciones gestionadas por el administrador - CORREGIDO"""
        
        # Si es BOSS, puede ver todas las ubicaciones
        admin = self.db.query(User).filter(User.id == admin_id).first()
        if admin and admin.role == "boss":
            return self.db.query(Location)\
                .filter(Location.is_active == True)\
                .order_by(Location.name)\
                .all()
        
        # Para administradores, solo ubicaciones asignadas
        return self.db.query(Location)\
            .join(AdminLocationAssignment, Location.id == AdminLocationAssignment.location_id)\
            .filter(
                AdminLocationAssignment.admin_id == admin_id,
                AdminLocationAssignment.is_active == True,
                Location.is_active == True
            )\
            .order_by(Location.name)\
            .all()
    
    def get_users_by_admin(self, admin_id: int) -> List[User]:
        """Obtener usuarios gestionados por un administrador - CORREGIDO"""
        
        # Si es BOSS, puede ver todos los usuarios
        admin = self.db.query(User).filter(User.id == admin_id).first()
        if admin and admin.role == "boss":
            return self.db.query(User)\
                .filter(User.role.in_(["vendedor", "bodeguero", "corredor", "administrador"]))\
                .filter(User.is_active == True)\
                .order_by(User.created_at.desc())\
                .all()
        
        # Para administradores, solo usuarios en ubicaciones asignadas
        managed_location_ids = self.db.query(AdminLocationAssignment.location_id)\
            .filter(
                AdminLocationAssignment.admin_id == admin_id,
                AdminLocationAssignment.is_active == True
            ).subquery()
        
        return self.db.query(User)\
            .join(UserLocationAssignment, User.id == UserLocationAssignment.user_id)\
            .filter(
                UserLocationAssignment.location_id.in_(managed_location_ids),
                UserLocationAssignment.is_active == True,
                User.role.in_(["vendedor", "bodeguero", "corredor"]),
                User.is_active == True
            )\
            .distinct()\
            .order_by(User.created_at.desc())\
            .all()
    
    def assign_user_to_location(self, assignment_data: dict) -> Dict[str, Any]:
        """Asignar usuario a ubicación"""
        
        # Verificar que usuario y ubicación existen
        user = self.db.query(User).filter(User.id == assignment_data["user_id"]).first()
        location = self.db.query(Location).filter(Location.id == assignment_data["location_id"]).first()
        
        if not user or not location:
            return {"success": False, "error": "Usuario o ubicación no encontrados"}
        
        # Actualizar ubicación principal del usuario
        user.location_id = assignment_data["location_id"]
        
        # Crear asignación específica (si la tabla existe)
        try:
            assignment = UserLocationAssignment(
                user_id=assignment_data["user_id"],
                location_id=assignment_data["location_id"],
                role_in_location=assignment_data.get("role_in_location"),
                start_date=assignment_data.get("start_date", date.today()),
                notes=assignment_data.get("notes")
            )
            self.db.add(assignment)
        except Exception:
            pass  # Tabla podría no existir aún
        
        self.db.commit()
        
        return {
            "success": True,
            "user_name": user.full_name,
            "location_name": location.name,
            "assignment_date": date.today()
        }
    
    # ==================== GESTIÓN DE UBICACIONES ====================
    
    
    def get_location_stats(self, location_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        """Obtener estadísticas de una ubicación - CORREGIDO"""
        
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return {}
        
        try:
            # Ventas del período
            sales_query = self.db.query(func.sum(Sale.total_amount), func.count(Sale.id))\
                .filter(
                    Sale.location_id == location_id,
                    func.date(Sale.sale_date) >= start_date,
                    func.date(Sale.sale_date) <= end_date
                ).first()
            
            total_sales = sales_query[0] or Decimal('0')
            total_transactions = sales_query[1] or 0
            
            # ✅ CORREGIDO: Usar location_name en lugar de location_id
            products_count = self.db.query(func.count(Product.id))\
                .filter(Product.location_name == location.name, Product.is_active == 1).scalar() or 0
            
            # Stock bajo usando location_name
            low_stock_count = self.db.query(func.count(ProductSize.id))\
                .join(Product, Product.id == ProductSize.product_id)\
                .filter(
                    Product.location_name == location.name,
                    ProductSize.quantity < 5,
                    ProductSize.quantity > 0,
                    Product.is_active == 1
                ).scalar() or 0
            
            # Valor total del inventario
            inventory_value = self.db.query(func.sum(Product.unit_price * Product.total_quantity))\
                .filter(Product.location_name == location.name, Product.is_active == 1).scalar() or Decimal('0')
            
            # Usuarios activos en la ubicación
            active_users_count = self.db.query(func.count(User.id))\
                .filter(User.location_id == location_id, User.is_active == True).scalar() or 0
            
            return {
                "location_id": location.id,
                "location_name": location.name,
                "location_type": location.type,
                "period_start": start_date,
                "period_end": end_date,
                "daily_sales": total_sales,
                "total_transactions": total_transactions,
                "total_products": products_count,
                "low_stock_alerts": low_stock_count,
                "inventory_value": float(inventory_value),
                "active_users": active_users_count,
                "average_ticket": float(total_sales / total_transactions) if total_transactions > 0 else 0.0
            }
        
        except Exception as e:
            print(f"Error calculando estadísticas para ubicación {location_id}: {e}")
            # Devolver estructura básica en caso de error
            return {
                "location_id": location.id,
                "location_name": location.name,
                "location_type": location.type,
                "period_start": start_date,
                "period_end": end_date,
                "daily_sales": Decimal('0'),
                "total_transactions": 0,
                "total_products": 0,
                "low_stock_alerts": 0,
                "inventory_value": 0.0,
                "active_users": 0,
                "average_ticket": 0.0
            }
    
    # ==================== COSTOS OPERATIVOS ====================
    
    def create_cost_configuration(self, cost_data: dict, admin_id: int) -> Dict[str, Any]:
        """Crear configuración de costo"""
        
        # En producción, esto se almacenaría en una tabla específica de costos
        # Por ahora, lo registramos como un expense especial
        expense_data = {
            "location_id": cost_data["location_id"],
            "user_id": admin_id,
            "concept": f"CONFIG_{cost_data['cost_type'].upper()}",
            "amount": cost_data["amount"],
            "receipt_image": None,
            "expense_date": cost_data["effective_date"],
            "notes": f"Configuración {cost_data['cost_type']}: {cost_data['description']} - Frecuencia: {cost_data['frequency']}"
        }
        
        db_expense = Expense(**expense_data)
        self.db.add(db_expense)
        self.db.commit()
        self.db.refresh(db_expense)
        
        return {
            "id": db_expense.id,
            "success": True,
            "cost_type": cost_data["cost_type"],
            "amount": cost_data["amount"],
            "frequency": cost_data["frequency"]
        }
    
    def get_cost_configurations(self, location_id: int) -> List[Dict[str, Any]]:
        """Obtener configuraciones de costo por ubicación"""
        
        costs = self.db.query(Expense)\
            .filter(
                Expense.location_id == location_id,
                Expense.concept.like("CONFIG_%")
            )\
            .order_by(desc(Expense.expense_date))\
            .all()
        
        return [
            {
                "id": cost.id,
                "cost_type": cost.concept.replace("CONFIG_", "").lower(),
                "amount": cost.amount,
                "description": cost.notes,
                "effective_date": cost.expense_date,
                "created_by": cost.user.full_name if cost.user else "Unknown"
            } for cost in costs
        ]
    
    # ==================== VENTAS AL POR MAYOR ====================
    
    def create_wholesale_sale(self, sale_data: dict, admin_id: int) -> Dict[str, Any]:
        """Crear venta al por mayor"""
        
        # Calcular totales
        items_total = sum(item["quantity"] * item["unit_price"] for item in sale_data["items"])
        discount_amount = items_total * (sale_data.get("discount_percentage", 0) / 100)
        final_amount = items_total - discount_amount
        
        # Crear venta principal
        sale = Sale(
            seller_id=admin_id,
            location_id=sale_data["location_id"],
            total_amount=final_amount,
            sale_date=datetime.now(),
            status="completed",
            notes=f"VENTA MAYORISTA - Cliente: {sale_data['customer_name']} ({sale_data['customer_document']}) - {sale_data.get('notes', '')}"
        )
        self.db.add(sale)
        self.db.flush()
        
        # Crear items de venta
        for item in sale_data["items"]:
            sale_item = SaleItem(
                sale_id=sale.id,
                sneaker_reference_code=item["reference_code"],
                brand=item.get("brand", "Unknown"),
                model=item.get("model", "Unknown"),
                color=item.get("color", "Unknown"),
                size=item["size"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["quantity"] * item["unit_price"]
            )
            self.db.add(sale_item)
            
            # Actualizar inventario
            self._update_inventory_for_sale(
                reference_code=item["reference_code"],
                size=item["size"],
                quantity=item["quantity"],
                location_id=sale_data["location_id"]
            )
        
        self.db.commit()
        self.db.refresh(sale)
        
        return {
            "id": sale.id,
            "total_amount": items_total,
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "items_count": len(sale_data["items"]),
            "sale_date": sale.sale_date
        }
    
    def _update_inventory_for_sale(self, reference_code: str, size: str, quantity: int, location_id: int):
        """Actualizar inventario después de venta"""
        
        product = self.db.query(Product)\
            .filter(
                Product.reference_code == reference_code,
                Product.location_id == location_id
            ).first()
        
        if product:
            product_size = self.db.query(ProductSize)\
                .filter(
                    ProductSize.product_id == product.id,
                    ProductSize.size == size
                ).first()
            
            if product_size and product_size.quantity >= quantity:
                old_quantity = product_size.quantity
                product_size.quantity -= quantity
                
                # Registrar cambio de inventario
                inventory_change = InventoryChange(
                    product_id=product.id,
                    change_type="wholesale_sale",
                    size=size,
                    quantity_before=old_quantity,
                    quantity_after=product_size.quantity,
                    notes=f"Venta mayorista - Reducción por venta de {quantity} unidades"
                )
                self.db.add(inventory_change)
    
    # ==================== REPORTES ====================
    
    def generate_sales_report(
        self, 
        location_ids: List[int], 
        start_date: date, 
        end_date: date,
        user_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """Generar reporte de ventas"""
        
        reports = []
        
        for location_id in location_ids:
            location = self.db.query(Location).filter(Location.id == location_id).first()
            if not location:
                continue
            
            # Query base de ventas
            sales_query = self.db.query(Sale)\
                .filter(
                    Sale.location_id == location_id,
                    func.date(Sale.sale_date) >= start_date,
                    func.date(Sale.sale_date) <= end_date
                )
            
            if user_ids:
                sales_query = sales_query.filter(Sale.seller_id.in_(user_ids))
            
            sales = sales_query.all()
            
            # Calcular métricas
            total_sales = sum(sale.total_amount for sale in sales)
            total_transactions = len(sales)
            average_ticket = total_sales / total_transactions if total_transactions > 0 else Decimal('0')
            
            # Top productos (simplificado)
            top_products_query = self.db.query(
                SaleItem.sneaker_reference_code,
                SaleItem.brand,
                SaleItem.model,
                func.sum(SaleItem.quantity).label('total_quantity'),
                func.sum(SaleItem.total_price).label('total_value')
            ).join(Sale, Sale.id == SaleItem.sale_id)\
             .filter(
                 Sale.location_id == location_id,
                 func.date(Sale.sale_date) >= start_date,
                 func.date(Sale.sale_date) <= end_date
             ).group_by(
                 SaleItem.sneaker_reference_code,
                 SaleItem.brand,
                 SaleItem.model
             ).order_by(desc('total_quantity'))\
             .limit(10).all()
            
            top_products = [
                {
                    "reference_code": prod[0],
                    "brand": prod[1],
                    "model": prod[2],
                    "total_quantity": int(prod[3]),
                    "total_value": float(prod[4])
                } for prod in top_products_query
            ]
            
            # Ventas por día
            sales_by_day_query = self.db.query(
                func.date(Sale.sale_date).label('sale_date'),
                func.sum(Sale.total_amount).label('daily_total'),
                func.count(Sale.id).label('daily_count')
            ).filter(
                Sale.location_id == location_id,
                func.date(Sale.sale_date) >= start_date,
                func.date(Sale.sale_date) <= end_date
            ).group_by(func.date(Sale.sale_date))\
             .order_by('sale_date').all()
            
            sales_by_day = [
                {
                    "date": str(day[0]),
                    "total_sales": float(day[1]),
                    "transactions": int(day[2])
                } for day in sales_by_day_query
            ]
            
            # Ventas por usuario
            sales_by_user_query = self.db.query(
                User.first_name,
                User.last_name,
                func.sum(Sale.total_amount).label('user_total'),
                func.count(Sale.id).label('user_count')
            ).join(Sale, Sale.seller_id == User.id)\
             .filter(
                 Sale.location_id == location_id,
                 func.date(Sale.sale_date) >= start_date,
                 func.date(Sale.sale_date) <= end_date
             ).group_by(User.id, User.first_name, User.last_name)\
             .order_by(desc('user_total')).all()
            
            sales_by_user = [
                {
                    "user_name": f"{user[0]} {user[1]}",
                    "total_sales": float(user[2]),
                    "transactions": int(user[3])
                } for user in sales_by_user_query
            ]
            
            reports.append({
                "location_id": location_id,
                "location_name": location.name,
                "period_start": start_date,
                "period_end": end_date,
                "total_sales": float(total_sales),
                "total_transactions": total_transactions,
                "average_ticket": float(average_ticket),
                "top_products": top_products,
                "sales_by_day": sales_by_day,
                "sales_by_user": sales_by_user
            })
        
        return reports
    
    # ==================== APROBACIÓN DE DESCUENTOS ====================
    
    def get_pending_discount_requests(self, admin_id: int) -> List[DiscountRequest]:
        """Obtener solicitudes de descuento pendientes"""
        return self.db.query(DiscountRequest)\
            .filter(DiscountRequest.status == "pending")\
            .order_by(DiscountRequest.requested_at)\
            .all()
    
    def approve_discount_request(
        self, 
        request_id: int, 
        approved: bool, 
        admin_id: int, 
        admin_notes: Optional[str] = None
    ) -> Optional[DiscountRequest]:
        """Aprobar o rechazar solicitud de descuento"""
        
        discount_request = self.db.query(DiscountRequest)\
            .filter(DiscountRequest.id == request_id).first()
        
        if not discount_request:
            return None
        
        discount_request.status = "approved" if approved else "rejected"
        discount_request.approved_by_user_id = admin_id
        discount_request.approved_at = datetime.now()
        discount_request.admin_notes = admin_notes
        
        self.db.commit()
        self.db.refresh(discount_request)
        
        return discount_request
    
    # ==================== SUPERVISIÓN DE TRANSFERENCIAS ====================
    
    def get_transfers_overview(self, location_ids: List[int]) -> Dict[str, Any]:
        """Obtener resumen de transferencias"""
        
        transfers = self.db.query(TransferRequest)\
            .filter(
                or_(
                    TransferRequest.source_location_id.in_(location_ids),
                    TransferRequest.destination_location_id.in_(location_ids)
                )
            ).all()
        
        summary = {
            "total_transfers": len(transfers),
            "by_status": {},
            "by_priority": {},
            "avg_processing_time": 0,
            "recent_transfers": []
        }
        
        # Agrupar por estado
        for transfer in transfers:
            status = transfer.status
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
            
            purpose = transfer.purpose
            summary["by_priority"][purpose] = summary["by_priority"].get(purpose, 0) + 1
        
        # Transferencias recientes
        recent = sorted(transfers, key=lambda x: x.requested_at, reverse=True)[:10]
        summary["recent_transfers"] = [
            {
                "id": t.id,
                "reference_code": t.sneaker_reference_code,
                "model": t.model,
                "size": t.size,
                "quantity": t.quantity,
                "status": t.status,
                "purpose": t.purpose,
                "requested_at": t.requested_at
            } for t in recent
        ]
        
        return summary
    
    # ==================== PERFORMANCE DE USUARIOS ====================
    
    def get_user_performance(
        self, 
        user_id: int, 
        start_date: date, 
        end_date: date
    ) -> Dict[str, Any]:
        """Obtener performance de un usuario específico"""
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}
        
        performance = {
            "user_id": user_id,
            "user_name": user.full_name,
            "role": user.role,
            "location_id": user.location_id,
            "location_name": user.location.name if user.location else "N/A",
            "period_start": start_date,
            "period_end": end_date,
            "metrics": {}
        }
        
        if user.role == "vendedor":
            # Métricas de vendedor
            sales = self.db.query(Sale)\
                .filter(
                    Sale.seller_id == user_id,
                    func.date(Sale.sale_date) >= start_date,
                    func.date(Sale.sale_date) <= end_date
                ).all()
            
            total_sales = sum(sale.total_amount for sale in sales)
            total_transactions = len(sales)
            avg_ticket = total_sales / total_transactions if total_transactions > 0 else Decimal('0')
            
            # Productos vendidos
            products_sold = self.db.query(func.sum(SaleItem.quantity))\
                .join(Sale, Sale.id == SaleItem.sale_id)\
                .filter(
                    Sale.seller_id == user_id,
                    func.date(Sale.sale_date) >= start_date,
                    func.date(Sale.sale_date) <= end_date
                ).scalar() or 0
            
            # Descuentos solicitados
            discounts_requested = self.db.query(func.count(DiscountRequest.id))\
                .filter(
                    DiscountRequest.requester_user_id == user_id,
                    func.date(DiscountRequest.requested_at) >= start_date,
                    func.date(DiscountRequest.requested_at) <= end_date
                ).scalar() or 0
            
            performance["metrics"] = {
                "total_sales": float(total_sales),
                "total_transactions": total_transactions,
                "average_ticket": float(avg_ticket),
                "products_sold": int(products_sold),
                "discounts_requested": discounts_requested
            }
        
        elif user.role == "bodeguero":
            # Métricas de bodeguero
            transfers_processed = self.db.query(func.count(TransferRequest.id))\
                .filter(
                    TransferRequest.warehouse_keeper_id == user_id,
                    func.date(TransferRequest.accepted_at) >= start_date,
                    func.date(TransferRequest.accepted_at) <= end_date
                ).scalar() or 0
            
            performance["metrics"] = {
                "transfers_processed": transfers_processed,
                "average_processing_time": 0,  # Se calcularía con timestamps
                "returns_handled": 0,  # Se calcularía con tabla de returns
                "discrepancies_reported": 0,  # Se calcularía con reportes de discrepancia
                "accuracy_rate": 100.0  # Se calcularía basado en errores
            }
        
        elif user.role == "corredor":
            # Métricas de corredor
            deliveries_completed = self.db.query(func.count(TransferRequest.id))\
                .filter(
                    TransferRequest.courier_id == user_id,
                    TransferRequest.status == "completed",
                    func.date(TransferRequest.delivered_at) >= start_date,
                    func.date(TransferRequest.delivered_at) <= end_date
                ).scalar() or 0
            
            performance["metrics"] = {
                "deliveries_completed": deliveries_completed,
                "average_delivery_time": 0,  # Se calcularía con timestamps
                "failed_deliveries": 0,  # Se calcularía con estado failed
                "incidents_reported": 0,  # Se calcularía con tabla de incidentes
                "on_time_rate": 100.0  # Se calcularía basado en tiempos estimados
            }
        
        return performance
    
    # ==================== DASHBOARD ADMINISTRATIVO ====================
    
    def get_admin_dashboard_data(self, admin_id: int) -> Dict[str, Any]:
        """Obtener datos completos del dashboard administrativo"""
        
        admin_user = self.db.query(User).filter(User.id == admin_id).first()
        managed_locations = self.get_managed_locations(admin_id)
        
        # Resumen diario
        today = date.today()
        daily_summary = {
            "total_sales": Decimal('0'),
            "total_transactions": 0,
            "active_users": 0,
            "locations_count": len(managed_locations)
        }
        
        for location in managed_locations:
            location_stats = self.get_location_stats(location.id, today, today)
            daily_summary["total_sales"] += Decimal(str(location_stats.get("daily_sales", 0)))
            daily_summary["active_users"] += location_stats.get("active_users", 0)
        
        # Tareas pendientes
        pending_tasks = {
            "discount_approvals": self.db.query(func.count(DiscountRequest.id))\
                .filter(DiscountRequest.status == "pending").scalar() or 0,
            "pending_transfers": self.db.query(func.count(TransferRequest.id))\
                .filter(TransferRequest.status == "pending").scalar() or 0,
            "low_stock_alerts": 0,  # Se calcularía con configuraciones de alerta
            "user_assignments": 0   # Se calcularía con asignaciones pendientes
        }
        
        # Actividades recientes (simplificado)
        recent_activities = [
            {
                "type": "sale",
                "description": "Nueva venta registrada",
                "timestamp": datetime.now(),
                "user": "Vendedor",
                "location": "Local Centro"
            }
        ]
        
        return {
            "admin_name": admin_user.full_name if admin_user else "Admin",
            "managed_locations": [self.get_location_stats(loc.id, today, today) for loc in managed_locations],
            "daily_summary": daily_summary,
            "pending_tasks": pending_tasks,
            "performance_overview": {
                "avg_sales_per_location": float(daily_summary["total_sales"]) / len(managed_locations) if managed_locations else 0,
                "total_users_managed": daily_summary["active_users"],
                "locations_managed": len(managed_locations)
            },
            "alerts_summary": {
                "critical": 0,
                "warning": pending_tasks["low_stock_alerts"],
                "info": pending_tasks["pending_transfers"]
            },
            "recent_activities": recent_activities
        }