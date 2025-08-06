# app/modules/admin/service.py
import json
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal

from .repository import AdminRepository
from .schemas import *
from app.shared.database.models import User, Location

class AdminService:
    """
    Servicio principal para todas las operaciones del administrador
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminRepository(db)
    
    # ==================== AD003 & AD004: CREAR USUARIOS ====================
    
    async def create_user(
        self, 
        user_data: UserCreate, 
        admin: User
    ) -> UserResponse:
        """
        AD003: Crear usuarios vendedores en locales asignados
        AD004: Crear usuarios bodegueros en bodegas asignadas
        """
        
        # Validar que el email no existe
        existing_user = self.db.query(User)\
            .filter(User.email == user_data.email.lower()).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email ya está en uso"
            )
        
        # Validar ubicación si se especifica
        if user_data.location_id:
            location = self.db.query(Location)\
                .filter(Location.id == user_data.location_id).first()
            
            if not location:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Ubicación no encontrada"
                )
            
            # Validar que el tipo de ubicación coincida con el rol
            if user_data.role == UserRole.VENDEDOR and location.type != "local":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Vendedores deben asignarse a locales"
                )
            elif user_data.role == UserRole.BODEGUERO and location.type != "bodega":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Bodegueros deben asignarse a bodegas"
                )
        
        # Crear usuario
        user_dict = user_data.dict()
        user_dict["email"] = user_dict["email"].lower()
        
        db_user = self.repository.create_user(user_dict)
        
        return UserResponse(
            id=db_user.id,
            email=db_user.email,
            first_name=db_user.first_name,
            last_name=db_user.last_name,
            full_name=db_user.full_name,
            role=db_user.role,
            location_id=db_user.location_id,
            location_name=db_user.location.name if db_user.location else None,
            is_active=db_user.is_active,
            created_at=db_user.created_at
        )
    
    # ==================== AD005 & AD006: ASIGNAR USUARIOS ====================
    
    async def assign_user_to_location(
        self, 
        assignment: UserAssignment, 
        admin: User
    ) -> Dict[str, Any]:
        """
        AD005: Asignar vendedores a locales específicos
        AD006: Asignar bodegueros a bodegas específicas
        """
        
        # Validar usuario
        user = self.db.query(User).filter(User.id == assignment.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Validar ubicación
        location = self.db.query(Location).filter(Location.id == assignment.location_id).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación no encontrada"
            )
        
        # Validar compatibilidad rol-ubicación
        if user.role == "vendedor" and location.type != "local":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vendedores solo pueden asignarse a locales"
            )
        elif user.role == "bodeguero" and location.type != "bodega":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bodegueros solo pueden asignarse a bodegas"
            )
        
        # Realizar asignación
        assignment_data = assignment.dict()
        result = self.repository.assign_user_to_location(assignment_data)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
    
    # ==================== AD001 & AD002: GESTIÓN DE UBICACIONES ====================
    
    async def get_managed_locations(self, admin: User) -> List[LocationResponse]:
        """
        AD001: Gestionar múltiples locales de venta asignados
        AD002: Supervisar múltiples bodegas bajo su responsabilidad
        """
        
        locations = self.repository.get_managed_locations(admin.id)
        
        location_responses = []
        for location in locations:
            # Calcular estadísticas básicas
            users_count = self.db.query(User)\
                .filter(User.location_id == location.id, User.is_active == True).count()
            
            products_count = self.db.query(Product)\
                .filter(Product.location_id == location.id, Product.is_active == 1).count()
            
            # Valor del inventario (simplificado)
            inventory_value = self.db.query(func.sum(Product.price))\
                .filter(Product.location_id == location.id, Product.is_active == 1).scalar() or Decimal('0')
            
            location_responses.append(LocationResponse(
                id=location.id,
                name=location.name,
                type=location.type,
                address=location.address,
                phone=location.phone,
                is_active=location.is_active,
                created_at=location.created_at,
                assigned_users_count=users_count,
                total_products=products_count,
                total_inventory_value=inventory_value
            ))
        
        return location_responses
    
    # ==================== AD007 & AD008: CONFIGURAR COSTOS ====================
    
    async def configure_cost(
        self, 
        cost_config: CostConfiguration, 
        admin: User
    ) -> CostResponse:
        """
        AD007: Configurar costos fijos (arriendo, servicios, nómina)
        AD008: Configurar costos variables (mercancía, comisiones)
        """
        
        # Validar ubicación
        location = self.db.query(Location)\
            .filter(Location.id == cost_config.location_id).first()
        
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación no encontrada"
            )
        
        # Crear configuración de costo
        cost_data = cost_config.dict()
        result = self.repository.create_cost_configuration(cost_data, admin.id)
        
        return CostResponse(
            id=result["id"],
            location_id=cost_config.location_id,
            location_name=location.name,
            cost_type=cost_config.cost_type.value,
            amount=cost_config.amount,
            frequency=cost_config.frequency,
            description=cost_config.description,
            is_active=cost_config.is_active,
            effective_date=cost_config.effective_date,
            created_by_user_id=admin.id,
            created_by_name=admin.full_name,
            created_at=datetime.now()
        )
    
    # ==================== AD009: VENTAS AL POR MAYOR ====================
    
    async def process_wholesale_sale(
        self, 
        sale_data: WholesaleSaleCreate, 
        admin: User
    ) -> WholesaleSaleResponse:
        """
        AD009: Procesar ventas al por mayor
        """
        
        # Validar ubicación
        location = self.db.query(Location)\
            .filter(Location.id == sale_data.location_id).first()
        
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación no encontrada"
            )
        
        # Validar disponibilidad de productos
        for item in sale_data.items:
            availability = self._check_product_availability(
                item["reference_code"],
                item["size"],
                item["quantity"],
                sale_data.location_id
            )
            
            if not availability["available"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente para {item['reference_code']} talla {item['size']}"
                )
        
        # Procesar venta
        sale_dict = sale_data.dict()
        result = self.repository.create_wholesale_sale(sale_dict, admin.id)
        
        return WholesaleSaleResponse(
            id=result["id"],
            customer_name=sale_data.customer_name,
            customer_document=sale_data.customer_document,
            customer_phone=sale_data.customer_phone,
            location_id=sale_data.location_id,
            location_name=location.name,
            total_amount=result["total_amount"],
            discount_amount=result["discount_amount"],
            final_amount=result["final_amount"],
            payment_method=sale_data.payment_method,
            sale_date=result["sale_date"],
            processed_by_user_id=admin.id,
            processed_by_name=admin.full_name,
            items_count=result["items_count"],
            notes=sale_data.notes
        )
    
    # ==================== AD010: REPORTES DE VENTAS ====================
    
    async def generate_sales_report(
        self, 
        filters: ReportFilter, 
        admin: User
    ) -> List[SalesReport]:
        """
        AD010: Generar reportes de ventas por local y período
        """
        
        # Si no se especifican ubicaciones, usar las gestionadas por el admin
        if not filters.location_ids:
            managed_locations = self.repository.get_managed_locations(admin.id)
            filters.location_ids = [loc.id for loc in managed_locations]
        
        # Generar reportes
        reports_data = self.repository.generate_sales_report(
            location_ids=filters.location_ids,
            start_date=filters.start_date,
            end_date=filters.end_date,
            user_ids=filters.user_ids
        )
        
        return [
            SalesReport(
                location_id=report["location_id"],
                location_name=report["location_name"],
                period_start=report["period_start"],
                period_end=report["period_end"],
                total_sales=Decimal(str(report["total_sales"])),
                total_transactions=report["total_transactions"],
                average_ticket=Decimal(str(report["average_ticket"])),
                top_products=report["top_products"],
                sales_by_day=report["sales_by_day"],
                sales_by_user=report["sales_by_user"]
            ) for report in reports_data
        ]
    
    # ==================== AD011: ALERTAS DE INVENTARIO ====================
    
    async def configure_inventory_alert(
        self, 
        alert_config: InventoryAlert, 
        admin: User
    ) -> InventoryAlertResponse:
        """
        AD011: Configurar alertas de inventario mínimo
        """
        
        # Validar ubicación
        location = self.db.query(Location)\
            .filter(Location.id == alert_config.location_id).first()
        
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación no encontrada"
            )
        
        # En producción, esto se almacenaría en una tabla de alertas
        # Por ahora, creamos un registro en inventory_changes
        from app.shared.database.models import InventoryChange
        
        alert_record = InventoryChange(
            product_id=None,
            change_type="inventory_alert_config",
            quantity_before=0,
            quantity_after=alert_config.threshold_value,
            user_id=admin.id,
            notes=f"ALERTA CONFIG: {alert_config.alert_type.value} - Umbral: {alert_config.threshold_value} - Emails: {','.join(alert_config.notification_emails)} - Producto: {alert_config.product_reference or 'TODOS'}"
        )
        
        self.db.add(alert_record)
        self.db.commit()
        self.db.refresh(alert_record)
        
        return InventoryAlertResponse(
            id=alert_record.id,
            location_id=alert_config.location_id,
            location_name=location.name,
            alert_type=alert_config.alert_type.value,
            threshold_value=alert_config.threshold_value,
            product_reference=alert_config.product_reference,
            notification_emails=alert_config.notification_emails,
            is_active=alert_config.is_active,
            created_by_user_id=admin.id,
            created_by_name=admin.full_name,
            created_at=alert_record.created_at,
            last_triggered=None
        )
    
    # ==================== AD012: APROBAR DESCUENTOS ====================
    
    async def approve_discount_request(
        self, 
        approval: DiscountApproval, 
        admin: User
    ) -> DiscountRequestResponse:
        """
        AD012: Aprobar solicitudes de descuento de vendedores
        """
        
        # Procesar aprobación
        discount_request = self.repository.approve_discount_request(
            request_id=approval.discount_request_id,
            approved=approval.approved,
            admin_id=admin.id,
            admin_notes=approval.admin_notes
        )
        
        if not discount_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud de descuento no encontrada"
            )
        
        return DiscountRequestResponse(
            id=discount_request.id,
            sale_id=discount_request.sale_id,
            requester_user_id=discount_request.requester_user_id,
            requester_name=discount_request.requester.full_name if discount_request.requester else "Unknown",
            location_id=discount_request.location_id,
            location_name=discount_request.location.name if discount_request.location else "Unknown",
            original_amount=discount_request.original_amount,
            discount_amount=discount_request.discount_amount,
            discount_percentage=discount_request.discount_percentage,
            reason=discount_request.reason,
            status=discount_request.status,
            requested_at=discount_request.requested_at,
            approved_by_user_id=discount_request.approved_by_user_id,
            approved_by_name=admin.full_name,
            approved_at=discount_request.approved_at,
            admin_notes=discount_request.admin_notes
        )
    
    async def get_pending_discount_requests(self, admin: User) -> List[DiscountRequestResponse]:
        """
        Obtener solicitudes de descuento pendientes de aprobación
        """
        
        requests = self.repository.get_pending_discount_requests(admin.id)
        
        return [
            DiscountRequestResponse(
                id=req.id,
                sale_id=req.sale_id,
                requester_user_id=req.requester_user_id,
                requester_name=req.requester.full_name if req.requester else "Unknown",
                location_id=req.location_id,
                location_name=req.location.name if req.location else "Unknown",
                original_amount=req.original_amount,
                discount_amount=req.discount_amount,
                discount_percentage=req.discount_percentage,
                reason=req.reason,
                status=req.status,
                requested_at=req.requested_at,
                approved_by_user_id=None,
                approved_by_name=None,
                approved_at=None,
                admin_notes=None
            ) for req in requests
        ]
    
    # ==================== AD013: SUPERVISAR TRASLADOS ====================
    
    async def get_transfers_overview(self, admin: User) -> Dict[str, Any]:
        """
        AD013: Supervisar traslados entre locales y bodegas
        """
        
        managed_locations = self.repository.get_managed_locations(admin.id)
        location_ids = [loc.id for loc in managed_locations]
        
        return self.repository.get_transfers_overview(location_ids)
    
    # ==================== AD014: SUPERVISAR PERFORMANCE ====================
    
    async def get_users_performance(
        self, 
        admin: User, 
        start_date: date, 
        end_date: date,
        user_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        AD014: Supervisar performance de vendedores y bodegueros
        """
        
        # Obtener usuarios gestionados
        if not user_ids:
            managed_users = self.repository.get_users_by_admin(admin.id)
            user_ids = [user.id for user in managed_users]
        
        performance_data = []
        
        for user_id in user_ids:
            performance = self.repository.get_user_performance(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date
            )
            
            if performance:
                performance_data.append(performance)
        
        return performance_data
    
    # ==================== AD015: ASIGNACIÓN DE MODELOS ====================
    
    async def assign_product_model_to_warehouses(
        self, 
        assignment: ProductModelAssignment, 
        admin: User
    ) -> ProductModelAssignmentResponse:
        """
        AD015: Gestionar asignación de modelos a bodegas específicas
        """
        
        # Validar que el producto existe
        product = self.db.query(Product)\
            .filter(Product.reference_code == assignment.product_reference)\
            .first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado"
            )
        
        # Validar bodegas
        warehouses = self.db.query(Location)\
            .filter(
                Location.id.in_(assignment.assigned_warehouses),
                Location.type == "bodega",
                Location.is_active == True
            ).all()
        
        if len(warehouses) != len(assignment.assigned_warehouses):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Una o más bodegas no son válidas"
            )
        
        # En producción, esto se almacenaría en una tabla específica
        # Por ahora, registramos en inventory_changes
        from app.shared.database.models import InventoryChange
        
        assignment_record = InventoryChange(
            product_id=product.id,
            change_type="model_assignment",
            quantity_before=0,
            quantity_after=len(assignment.assigned_warehouses),
            user_id=admin.id,
            notes=f"ASIGNACIÓN MODELO: {assignment.product_reference} - Bodegas: {','.join([w.name for w in warehouses])} - Reglas: {assignment.distribution_rules}"
        )
        
        self.db.add(assignment_record)
        self.db.commit()
        self.db.refresh(assignment_record)
        
        # Buscar bodega prioritaria
        priority_warehouse = None
        if assignment.priority_warehouse_id:
            priority_warehouse = next(
                (w for w in warehouses if w.id == assignment.priority_warehouse_id), 
                None
            )
        
        return ProductModelAssignmentResponse(
            id=assignment_record.id,
            product_reference=assignment.product_reference,
            product_brand=product.brand,
            product_model=product.model,
            assigned_warehouses=[
                {
                    "warehouse_id": w.id,
                    "warehouse_name": w.name,
                    "address": w.address
                } for w in warehouses
            ],
            distribution_rules=assignment.distribution_rules,
            priority_warehouse_id=assignment.priority_warehouse_id,
            priority_warehouse_name=priority_warehouse.name if priority_warehouse else None,
            min_stock_per_warehouse=assignment.min_stock_per_warehouse,
            max_stock_per_warehouse=assignment.max_stock_per_warehouse,
            assigned_by_user_id=admin.id,
            assigned_by_name=admin.full_name,
            assigned_at=assignment_record.created_at
        )
    
    # ==================== DASHBOARD ADMINISTRATIVO ====================
    
    async def get_admin_dashboard(self, admin: User) -> AdminDashboard:
        """
        Dashboard completo del administrador con todas las métricas
        """
        
        dashboard_data = self.repository.get_admin_dashboard_data(admin.id)
        
        managed_locations = [
            LocationStats(
                location_id=loc["location_id"],
                location_name=loc["location_name"],
                location_type=loc["location_type"],
                daily_sales=Decimal(str(loc.get("daily_sales", 0))),
                monthly_sales=Decimal(str(loc.get("monthly_sales", 0))),
                total_products=loc.get("total_products", 0),
                low_stock_alerts=loc.get("low_stock_alerts", 0),
                pending_transfers=loc.get("pending_transfers", 0),
                active_users=loc.get("active_users", 0)
            ) for loc in dashboard_data["managed_locations"]
        ]
        
        return AdminDashboard(
            admin_name=dashboard_data["admin_name"],
            managed_locations=managed_locations,
            daily_summary=dashboard_data["daily_summary"],
            pending_tasks=dashboard_data["pending_tasks"],
            performance_overview=dashboard_data["performance_overview"],
            alerts_summary=dashboard_data["alerts_summary"],
            recent_activities=dashboard_data["recent_activities"]
        )
    
    # ==================== MÉTODOS AUXILIARES ====================
    
    def _check_product_availability(
        self, 
        reference_code: str, 
        size: str, 
        quantity: int, 
        location_id: int
    ) -> Dict[str, Any]:
        """Verificar disponibilidad de producto"""
        
        product = self.db.query(Product)\
            .filter(
                Product.reference_code == reference_code,
                Product.location_id == location_id,
                Product.is_active == 1
            ).first()
        
        if not product:
            return {"available": False, "reason": "Producto no encontrado"}
        
        from app.shared.database.models import ProductSize
        product_size = self.db.query(ProductSize)\
            .filter(
                ProductSize.product_id == product.id,
                ProductSize.size == size
            ).first()
        
        if not product_size or product_size.quantity < quantity:
            return {
                "available": False, 
                "reason": "Stock insuficiente",
                "available_quantity": product_size.quantity if product_size else 0
            }
        
        return {
            "available": True,
            "available_quantity": product_size.quantity
        }