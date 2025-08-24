# app/modules/admin/service.py
import json
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy import func 
from sqlalchemy.orm import Session
from decimal import Decimal
from app.shared.services.video_microservice_client import VideoMicroserviceClient
import uuid

from fastapi import APIRouter, Depends, Query, File, UploadFile, Form


from .repository import AdminRepository
from .schemas import *
from app.shared.database.models import User, Location ,AdminLocationAssignment , Product

class AdminService:
    """
    Servicio principal para todas las operaciones del administrador
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminRepository(db)
        self.video_client = VideoMicroserviceClient()
    
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
        
        # ====== VALIDACIÓN: VERIFICAR PERMISOS DE UBICACIÓN ======
        if user_data.location_id:
            can_manage = await self._can_admin_manage_location(admin.id, user_data.location_id)
            if not can_manage:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes permisos para crear usuarios en la ubicación {user_data.location_id}"
                )
        
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
        
        # ====== TRANSACCIÓN ÚNICA PARA CREAR USUARIO Y ASIGNACIÓN ======
        try:
            # 1. Crear usuario (SIN COMMIT AÚN)
            user_dict = user_data.dict()
            user_dict["email"] = user_dict["email"].lower()
            
            # Hashear password
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            
            hashed_password = pwd_context.hash(user_dict["password"])
            user_dict["password_hash"] = hashed_password
            del user_dict["password"]
            
            db_user = User(**user_dict)
            self.db.add(db_user)
            self.db.flush()  # Obtener ID sin hacer commit aún
            
            # 2. Crear asignación en UserLocationAssignment si se especifica ubicación
            if user_data.location_id:
                from app.shared.database.models import UserLocationAssignment
                
                assignment = UserLocationAssignment(
                    user_id=db_user.id,
                    location_id=user_data.location_id,
                    role_at_location=user_data.role.value,
                    is_active=True
                )
                self.db.add(assignment)
            
            # 3. Commit de toda la transacción
            self.db.commit()
            self.db.refresh(db_user)
            
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
            
        except Exception as e:
            # Rollback de toda la transacción si algo falla
            self.db.rollback()
            
            # Log del error específico
            print(f"Error detallado creando usuario: {e}")
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creando usuario y asignación: {str(e)}"
            )

    
    # ==================== AD005 & AD006: ASIGNAR USUARIOS ====================

    async def _can_admin_manage_location(self, admin_id: int, location_id: int) -> bool:
        """Verificar si un administrador puede gestionar una ubicación específica"""
        
        # BOSS puede gestionar cualquier ubicación
        admin = self.db.query(User).filter(User.id == admin_id).first()
        if admin and admin.role == "boss":
            return True
        
        # Para administradores, verificar asignación específica
        assignment = self.db.query(AdminLocationAssignment)\
            .filter(
                AdminLocationAssignment.admin_id == admin_id,
                AdminLocationAssignment.location_id == location_id,
                AdminLocationAssignment.is_active == True
            ).first()
        
        return assignment is not None

    async def assign_admin_to_locations(
        self, 
        assignment_data: AdminLocationAssignmentCreate,
        boss: User
    ) -> AdminLocationAssignmentResponse:
        """
        Asignar administrador a una ubicación específica
        Solo el BOSS puede hacer esto
        """
        
        # Validar que el usuario a asignar es administrador
        admin_user = self.db.query(User).filter(User.id == assignment_data.admin_id).first()
        if not admin_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Administrador no encontrado"
            )
        
        if admin_user.role != "administrador":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El usuario debe tener rol de administrador"
            )
        
        # Validar que la ubicación existe
        location = self.db.query(Location).filter(Location.id == assignment_data.location_id).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación no encontrada"
            )
        
        # Crear asignación
        assignment_dict = assignment_data.dict()
        assignment_dict["assigned_by_user_id"] = boss.id
        
        db_assignment = self.repository.create_admin_assignment(assignment_dict)
        
        return AdminLocationAssignmentResponse(
            id=db_assignment.id,
            admin_id=db_assignment.admin_id,
            admin_name=admin_user.full_name,
            location_id=db_assignment.location_id,
            location_name=location.name,
            location_type=location.type,
            is_active=db_assignment.is_active,
            assigned_at=db_assignment.assigned_at,
            assigned_by_name=boss.full_name,
            notes=db_assignment.notes
        )
    
    async def assign_admin_to_multiple_locations(
        self,
        bulk_assignment: AdminLocationAssignmentBulk,
        boss: User
    ) -> List[AdminLocationAssignmentResponse]:
        """
        Asignar administrador a múltiples ubicaciones
        """
        
        results = []
        
        for location_id in bulk_assignment.location_ids:
            assignment_data = AdminLocationAssignmentCreate(
                admin_id=bulk_assignment.admin_id,
                location_id=location_id,
                notes=bulk_assignment.notes
            )
            
            try:
                result = await self.assign_admin_to_locations(assignment_data, boss)
                results.append(result)
            except HTTPException as e:
                # Continuar con las otras ubicaciones si una falla
                continue
        
        return results
    
    async def get_admin_assignments(self, admin: User) -> List[AdminLocationAssignmentResponse]:
        """
        Obtener asignaciones de ubicaciones del administrador actual
        """
        
        assignments = self.repository.get_admin_assignments(admin.id)
        
        return [
            AdminLocationAssignmentResponse(
                id=assignment.id,
                admin_id=assignment.admin_id,
                admin_name=admin.full_name,
                location_id=assignment.location_id,
                location_name=assignment.location.name,
                location_type=assignment.location.type,
                is_active=assignment.is_active,
                assigned_at=assignment.assigned_at,
                assigned_by_name=assignment.assigned_by.full_name if assignment.assigned_by else None,
                notes=assignment.notes
            ) for assignment in assignments
        ]

    async def update_user(
        self,
        user_id: int,
        update_data: UserUpdate,
        admin: User
    ) -> UserResponse:
        """
        Actualizar usuario con validaciones de permisos
        
        **Validaciones:**
        - Admin solo puede actualizar usuarios en ubicaciones bajo su control
        - Si se cambia la ubicación, la nueva ubicación debe estar bajo su control
        - Validar compatibilidad rol-ubicación si se cambia ubicación
        """
        
        # 1. Buscar el usuario que se quiere actualizar
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # ====== VALIDACIÓN: ADMIN PUEDE GESTIONAR USUARIO ACTUAL ======
        if user.location_id:
            can_manage_current = await self._can_admin_manage_location(admin.id, user.location_id)
            if not can_manage_current:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes permisos para gestionar usuarios en la ubicación actual del usuario"
                )
        
        # ====== VALIDACIÓN: NUEVA UBICACIÓN BAJO CONTROL (si se especifica) ======
        update_dict = update_data.dict(exclude_unset=True)
        if "location_id" in update_dict and update_dict["location_id"] is not None:
            new_location_id = update_dict["location_id"]
            
            can_manage_new = await self._can_admin_manage_location(admin.id, new_location_id)
            if not can_manage_new:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes permisos para asignar usuarios a la ubicación {new_location_id}"
                )
            
            # Validar compatibilidad rol-ubicación
            new_location = self.db.query(Location).filter(Location.id == new_location_id).first()
            if not new_location:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Nueva ubicación no encontrada"
                )
            
            # Validar compatibilidad con el rol del usuario
            if user.role == "vendedor" and new_location.type != "local":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Vendedores solo pueden asignarse a locales"
                )
            elif user.role == "bodeguero" and new_location.type != "bodega":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Bodegueros solo pueden asignarse a bodegas"
                )
        
        # ====== REALIZAR ACTUALIZACIÓN ======
        try:
            # Actualizar campos del usuario
            for key, value in update_dict.items():
                if hasattr(user, key) and value is not None:
                    setattr(user, key, value)
            
            # Si se cambió la ubicación, actualizar también user_location_assignments
            if "location_id" in update_dict and update_dict["location_id"] is not None:
                from app.shared.database.models import UserLocationAssignment
                
                # Desactivar asignación anterior
                self.db.query(UserLocationAssignment)\
                    .filter(
                        UserLocationAssignment.user_id == user_id,
                        UserLocationAssignment.is_active == True
                    ).update({"is_active": False})
                
                # Crear nueva asignación
                new_assignment = UserLocationAssignment(
                    user_id=user_id,
                    location_id=update_dict["location_id"],
                    role_at_location=user.role,
                    is_active=True
                )
                self.db.add(new_assignment)
            
            self.db.commit()
            self.db.refresh(user)
            
            return UserResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                full_name=user.full_name,
                role=user.role,
                location_id=user.location_id,
                location_name=user.location.name if user.location else None,
                is_active=user.is_active,
                created_at=user.created_at
            )
            
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error actualizando usuario: {str(e)}"
            )
    
    async def remove_admin_assignment(
        self,
        admin_id: int,
        location_id: int,
        boss: User
    ) -> Dict[str, Any]:
        """
        Remover asignación de administrador a ubicación
        """
        
        success = self.repository.remove_admin_assignment(admin_id, location_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asignación no encontrada"
            )
        
        return {
            "success": True,
            "message": "Asignación removida correctamente",
            "removed_by": boss.full_name,
            "removed_at": datetime.now()
        }
    
    async def get_all_admin_assignments(self, boss: User) -> List[AdminLocationAssignmentResponse]:
        """
        Ver todas las asignaciones de administradores (solo para BOSS)
        """
        
        assignments = self.db.query(AdminLocationAssignment)\
            .filter(AdminLocationAssignment.is_active == True)\
            .join(User, AdminLocationAssignment.admin_id == User.id)\
            .join(Location, AdminLocationAssignment.location_id == Location.id)\
            .all()
        
        return [
            AdminLocationAssignmentResponse(
                id=assignment.id,
                admin_id=assignment.admin_id,
                admin_name=assignment.admin.full_name,
                location_id=assignment.location_id,
                location_name=assignment.location.name,
                location_type=assignment.location.type,
                is_active=assignment.is_active,
                assigned_at=assignment.assigned_at,
                assigned_by_name=assignment.assigned_by.full_name if assignment.assigned_by else None,
                notes=assignment.notes
            ) for assignment in assignments
        ]
    
    async def assign_user_to_location(
        self, 
        assignment: UserAssignment, 
        admin: User
    ) -> Dict[str, Any]:
        """
        AD005: Asignar vendedores a locales específicos
        AD006: Asignar bodegueros a bodegas específicas
        
        **VALIDACIONES DE PERMISOS AGREGADAS:**
        - Solo puede asignar usuarios que estén en ubicaciones bajo su control
        - Solo puede asignar a ubicaciones que él gestiona
        - Validar compatibilidad rol-ubicación
        - BOSS puede asignar cualquier usuario a cualquier ubicación
        """
        
        # 1. Buscar el usuario que se quiere asignar
        user = self.db.query(User).filter(User.id == assignment.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # ====== VALIDACIÓN: ADMIN PUEDE GESTIONAR USUARIO ACTUAL ======
        if user.location_id:
            can_manage_current_user = await self._can_admin_manage_location(admin.id, user.location_id)
            if not can_manage_current_user:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes permisos para gestionar el usuario {user.full_name}. "
                        f"El usuario está en una ubicación que no controlas."
                )
        else:
            # Si el usuario no tiene ubicación, solo BOSS puede asignarlo
            if admin.role != "boss":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo el BOSS puede asignar usuarios sin ubicación asignada"
                )
        
        # 2. Buscar la ubicación destino
        location = self.db.query(Location).filter(Location.id == assignment.location_id).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación destino no encontrada"
            )
        
        # ====== VALIDACIÓN: ADMIN PUEDE GESTIONAR UBICACIÓN DESTINO ======
        can_manage_destination = await self._can_admin_manage_location(admin.id, assignment.location_id)
        if not can_manage_destination:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos para asignar usuarios a {location.name}. "
                    f"Esta ubicación no está bajo tu control."
            )
        
        # ====== VALIDACIÓN: COMPATIBILIDAD ROL-UBICACIÓN ======
        if user.role == "vendedor" and location.type != "local":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede asignar vendedor {user.full_name} a {location.name} "
                    f"porque es de tipo '{location.type}'. Vendedores solo pueden ir a locales."
            )
        elif user.role == "bodeguero" and location.type != "bodega":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede asignar bodeguero {user.full_name} a {location.name} "
                    f"porque es de tipo '{location.type}'. Bodegueros solo pueden ir a bodegas."
            )
        
        # ====== REALIZAR ASIGNACIÓN ======
        try:
            # Actualizar ubicación principal del usuario
            old_location_name = user.location.name if user.location else "Sin ubicación"
            user.location_id = assignment.location_id
            
            # Desactivar asignaciones anteriores en user_location_assignments
            from app.shared.database.models import UserLocationAssignment
            
            self.db.query(UserLocationAssignment)\
                .filter(
                    UserLocationAssignment.user_id == assignment.user_id,
                    UserLocationAssignment.is_active == True
                ).update({"is_active": False})
            
            # Crear nueva asignación en user_location_assignments
            new_assignment = UserLocationAssignment(
                user_id=assignment.user_id,
                location_id=assignment.location_id,
                role_at_location=assignment.role_in_location or user.role,
                is_active=True
            )
            self.db.add(new_assignment)
            
            self.db.commit()
            self.db.refresh(user)
            
            return {
                "success": True,
                "message": f"Usuario {user.full_name} asignado correctamente",
                "user_name": user.full_name,
                "user_role": user.role,
                "previous_location": old_location_name,
                "new_location": location.name,
                "new_location_type": location.type,
                "assigned_by": admin.full_name,
                "assignment_date": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error realizando asignación: {str(e)}"
            )
    
    # ==================== AD001 & AD002: GESTIÓN DE UBICACIONES ====================
    
    async def get_managed_locations(self, admin: User) -> List[LocationResponse]:
        """
        AD001: Gestionar múltiples locales de venta asignados
        AD002: Supervisar múltiples bodegas bajo su responsabilidad
        """
        
        locations = self.repository.get_managed_locations(admin.id)
        
        location_responses = []
        for location in locations:
            try:
                # 1. Contar usuarios asignados a esta ubicación
                users_count = self.db.query(User)\
                    .filter(User.location_id == location.id, User.is_active == True).count()
                
                # 2. Contar productos usando location_name (según tu modelo)
                products_count = self.db.query(Product)\
                    .filter(Product.location_name == location.name, Product.is_active == 1).count()
                
                # 3. Calcular valor del inventario 
                # Sumar (unit_price * total_quantity) para valor real del inventario
                inventory_value_query = self.db.query(
                    func.sum(Product.unit_price * Product.total_quantity)
                ).filter(
                    Product.location_name == location.name, 
                    Product.is_active == 1
                ).scalar()
                
                inventory_value = inventory_value_query or Decimal('0')
                
            except Exception as e:
                # Si hay error calculando estadísticas, usar valores por defecto
                print(f"Warning: Error calculando stats para ubicación {location.name}: {e}")
                users_count = 0
                products_count = 0
                inventory_value = Decimal('0')
            
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
    
    async def process_video_inventory_entry(
        self,
        video_entry: VideoProductEntry,
        video_file: UploadFile,
        admin: User
    ) -> Dict[str, Any]:
        """
        AD016: Registro de inventario con video IA - VERSIÓN MICROSERVICIO
        
        Este método ahora es LIGERO - solo crea job y envía al microservicio
        """
        
        # 1. Validaciones rápidas
        warehouse = self.repository.get_location_by_id(video_entry.warehouse_location_id)
        if not warehouse or warehouse.type != "bodega":
            raise HTTPException(status_code=404, detail="Bodega no encontrada")
        
        if not self.repository.user_has_access_to_location(admin.id, warehouse.id):
            raise HTTPException(status_code=403, detail="No tienes acceso a esta bodega")
        
        # Validar tamaño de video
        max_size = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
        if video_file.size > max_size:
            raise HTTPException(
                status_code=400, 
                detail=f"Video no debe superar {settings.MAX_VIDEO_SIZE_MB}MB"
            )
        
        # 2. Crear job de procesamiento
        job_id = f"video_{uuid.uuid4().hex}"
        
        from app.shared.database.models import VideoProcessingJob
        video_job = VideoProcessingJob(
            job_id=job_id,
            warehouse_location_id=video_entry.warehouse_location_id,
            estimated_quantity=video_entry.estimated_quantity,
            product_brand=video_entry.product_brand,
            product_model=video_entry.product_model,
            expected_sizes=json.dumps(video_entry.expected_sizes) if video_entry.expected_sizes else None,
            notes=video_entry.notes,
            status="submitted",
            submitted_by_user_id=admin.id
        )
        
        self.db.add(video_job)
        self.db.commit()
        self.db.refresh(video_job)
        
        # 3. Preparar metadata para microservicio
        metadata = {
            "job_db_id": video_job.id,
            "warehouse_id": video_entry.warehouse_location_id,
            "warehouse_name": warehouse.name,
            "estimated_quantity": video_entry.estimated_quantity,
            "admin_id": admin.id,
            "admin_name": admin.full_name,
            "expected_brand": video_entry.product_brand,
            "expected_model": video_entry.product_model,
            "expected_sizes": video_entry.expected_sizes,
            "notes": video_entry.notes
        }
        
        try:
            # 4. Enviar al microservicio (async)
            microservice_response = await self.video_client.submit_video_for_processing(
                job_id=video_job.id,
                video_file=video_file,
                metadata=metadata
            )
            
            # 5. Actualizar estado
            video_job.status = "processing"
            self.db.commit()
            
            logger.info(f"✅ Video job {job_id} enviado al microservicio")
            
            return {
                "job_id": video_job.id,
                "job_uuid": job_id,
                "status": "processing",
                "message": "Video enviado para procesamiento. Recibirás notificación al completar.",
                "estimated_time_minutes": "2-5",
                "warehouse_name": warehouse.name,
                "microservice_response": microservice_response
            }
            
        except Exception as e:
            # Marcar job como fallido
            video_job.status = "failed"
            video_job.error_message = str(e)
            self.db.commit()
            
            logger.error(f"❌ Error enviando video job {job_id}: {e}")
            raise HTTPException(
                status_code=502, 
                detail=f"Error procesando video: {str(e)}"
            )
    
    async def get_video_processing_status(self, job_id: int, admin: User) -> Dict[str, Any]:
        """Consultar estado de procesamiento"""
        
        from app.shared.database.models import VideoProcessingJob
        job = self.db.query(VideoProcessingJob).filter(
            VideoProcessingJob.id == job_id,
            VideoProcessingJob.submitted_by_user_id == admin.id
        ).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        
        # Si está en procesamiento, consultar microservicio
        if job.status == "processing":
            try:
                microservice_status = await self.video_client.get_processing_status(job_id)
                # Actualizar progreso si cambió
                if microservice_status.get("progress_percentage") != job.progress_percentage:
                    job.progress_percentage = microservice_status.get("progress_percentage", 0)
                    self.db.commit()
            except:
                pass  # Si no responde, usar datos locales
        
        return {
            "job_id": job.id,
            "job_uuid": job.job_id,
            "status": job.status,
            "progress_percentage": job.progress_percentage,
            "warehouse_name": job.warehouse_location.name,
            "estimated_quantity": job.estimated_quantity,
            "submitted_at": job.submitted_at,
            "processing_started_at": job.processing_started_at,
            "processing_completed_at": job.processing_completed_at,
            "error_message": job.error_message,
            "detected_products": json.loads(job.detected_products) if job.detected_products else None,
            "created_products": json.loads(job.created_products) if job.created_products else None
        }
    
    async def _simulate_ai_processing(self, video_path: str, video_entry: VideoProductEntry) -> Dict[str, Any]:
        """
        Simular procesamiento de IA (en producción sería real)
        """
        import random
        
        # Simular resultados de IA
        brands = ["Nike", "Adidas", "Puma", "Reebok", "New Balance"]
        colors = ["Negro", "Blanco", "Azul", "Rojo", "Gris"]
        sizes = ["38", "39", "40", "41", "42", "43", "44"]
        
        detected_brand = video_entry.product_brand or random.choice(brands)
        detected_model = video_entry.product_model or f"Modelo-{random.randint(1000, 9999)}"
        
        return {
            "detected_brand": detected_brand,
            "detected_model": detected_model,
            "detected_colors": random.sample(colors, random.randint(1, 3)),
            "detected_sizes": video_entry.expected_sizes or random.sample(sizes, random.randint(3, 6)),
            "confidence_scores": {
                "brand": random.uniform(0.8, 0.98),
                "model": random.uniform(0.75, 0.95),
                "colors": random.uniform(0.85, 0.97),
                "sizes": random.uniform(0.80, 0.93),
                "overall": random.uniform(0.82, 0.95)
            },
            "bounding_boxes": [
                {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8, "label": "product"},
                {"x": 0.15, "y": 0.7, "width": 0.3, "height": 0.1, "label": "size_label"}
            ],
            "recommended_reference_code": f"{detected_brand[:3].upper()}-{detected_model[:4].upper()}-{random.randint(100, 999)}"
        }
    
    async def get_video_processing_history(
        self,
        limit: int,
        status: Optional[str],
        warehouse_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        admin_user: User
    ) -> List[VideoProcessingResponse]:
        """
        Obtener historial de videos procesados
        """
        # En producción, esto consultaría una tabla específica de videos
        # Por ahora, usamos inventory_changes con change_type="video_ai_training"
        
        from app.shared.database.models import InventoryChange, Location
        
        query = self.db.query(InventoryChange, Location)\
            .join(Location, InventoryChange.user_id == admin_user.id)\
            .filter(InventoryChange.change_type == "video_ai_training")
        
        if date_from:
            query = query.filter(InventoryChange.created_at >= date_from)
        
        if date_to:
            query = query.filter(InventoryChange.created_at <= date_to)
        
        records = query.limit(limit).all()
        
        # Simular respuestas
        results = []
        for record, location in records:
            results.append(VideoProcessingResponse(
                id=record.id,
                video_file_path=f"uploads/inventory_videos/video_{record.id}.mp4",
                warehouse_location_id=location.id,
                warehouse_name=location.name,
                estimated_quantity=record.quantity_after,
                processing_status="completed",
                ai_extracted_info={},
                detected_products=[],
                confidence_score=0.87,
                processed_by_user_id=record.user_id,
                processed_by_name=admin_user.full_name,
                processing_started_at=record.created_at,
                processing_completed_at=record.created_at,
                error_message=None,
                notes=record.notes
            ))
        
        return results
    
    async def get_video_processing_details(self, video_id: int, admin_user: User) -> VideoProcessingResponse:
        """
        Obtener detalles específicos de video procesado
        """
        from app.shared.database.models import InventoryChange
        
        record = self.db.query(InventoryChange)\
            .filter(
                InventoryChange.id == video_id,
                InventoryChange.change_type == "video_ai_training"
            ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Video no encontrado")
        
        # Simular respuesta detallada
        return VideoProcessingResponse(
            id=record.id,
            video_file_path=f"uploads/inventory_videos/video_{record.id}.mp4",
            warehouse_location_id=1,  # Se obtendría de la relación
            warehouse_name="Bodega Central",
            estimated_quantity=record.quantity_after,
            processing_status="completed",
            ai_extracted_info={
                "detected_brand": "Nike",
                "detected_model": "Air Max 270",
                "detected_colors": ["Negro", "Blanco"],
                "detected_sizes": ["40", "41", "42", "43"],
                "confidence_scores": {"overall": 0.92}
            },
            detected_products=[{
                "brand": "Nike",
                "model": "Air Max 270", 
                "colors": ["Negro", "Blanco"],
                "sizes": ["40", "41", "42", "43"],
                "confidence": 0.92
            }],
            confidence_score=0.92,
            processed_by_user_id=record.user_id,
            processed_by_name=admin_user.full_name,
            processing_started_at=record.created_at,
            processing_completed_at=record.created_at,
            error_message=None,
            notes=record.notes
        )