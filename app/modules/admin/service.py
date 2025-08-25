# app/modules/admin/service.py
import json
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any , Callable, Union
from fastapi import HTTPException, status
from sqlalchemy import func 
from sqlalchemy.orm import Session
from decimal import Decimal
from app.shared.services.video_microservice_client import VideoMicroserviceClient
from functools import wraps
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

    async def _validate_location_access(
        self, 
        admin: User, 
        location_id: int, 
        action: str = "gestionar"
    ) -> Location:
        """
        Validar acceso a ubicación específica
        
        Returns:
            Location: La ubicación validada
        """
        if not location_id:
            raise HTTPException(400, "ID de ubicación requerido")
            
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise HTTPException(404, f"Ubicación {location_id} no encontrada")
        
        can_manage = await self._can_admin_manage_location(admin.id, location_id)
        if not can_manage:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos para {action} en '{location.name}' ({location.type})"
            )
        
        return location
    
    async def _filter_managed_locations(
        self, 
        admin: User, 
        requested_location_ids: Optional[List[int]] = None
    ) -> List[int]:
        """Filtrar solo ubicaciones gestionadas"""
        managed_locations = self.repository.get_managed_locations(admin.id)
        managed_ids = [loc.id for loc in managed_locations]
        
        if requested_location_ids:
            invalid_ids = set(requested_location_ids) - set(managed_ids)
            if invalid_ids:
                invalid_names = []
                for inv_id in invalid_ids:
                    loc = self.db.query(Location).filter(Location.id == inv_id).first()
                    invalid_names.append(loc.name if loc else f"ID-{inv_id}")
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Sin permisos para ubicaciones: {', '.join(invalid_names)}"
                )
            return requested_location_ids
        
        return managed_ids
    
    async def _validate_user_access(
        self, 
        admin: User, 
        user_id: int, 
        action: str = "gestionar"
    ) -> User:
        """Validar acceso a usuario específico"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, f"Usuario {user_id} no encontrado")
        
        if user.location_id:
            await self._validate_location_access(admin, user.location_id, f"{action} usuario")
        elif admin.role != "boss":
            raise HTTPException(403, "Solo BOSS puede gestionar usuarios sin ubicación")
        
        return user
    
    async def _get_managed_user_ids(self, admin: User) -> List[int]:
        """Obtener IDs de usuarios gestionados"""
        managed_users = self.repository.get_users_by_admin(admin.id)
        return [user.id for user in managed_users]
    
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
    
    async def get_cost_configurations(
        self,
        admin: User,
        location_id: Optional[int] = None,
        cost_type: Optional[str] = None
    ) -> List[CostResponse]:
        """
        Obtener configuraciones de costos con validación de permisos
        """
        
        if location_id:
            # ✅ Validar acceso a ubicación específica
            location = await self._validate_location_access(
                admin, 
                location_id, 
                "ver configuraciones de costos"
            )
            
            costs_data = self.repository.get_cost_configurations(location_id)
            
            # Filtrar por tipo de costo si se especifica
            if cost_type:
                costs_data = [c for c in costs_data if c["cost_type"] == cost_type]
            
            return [CostResponse(**cost_data) for cost_data in costs_data]
        
        else:
            # ✅ Obtener de todas las ubicaciones gestionadas
            managed_location_ids = await self._filter_managed_locations(admin)
            
            all_costs = []
            for loc_id in managed_location_ids:
                location_costs = self.repository.get_cost_configurations(loc_id)
                
                # Filtrar por tipo si se especifica
                if cost_type:
                    location_costs = [c for c in location_costs if c["cost_type"] == cost_type]
                
                all_costs.extend(location_costs)
            
            return [CostResponse(**cost_data) for cost_data in all_costs]
    
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
        """AD007 & AD008: Configurar costos con validación"""
        
        # ✅ Validar acceso a la ubicación
        location = await self._validate_location_access(
            admin, 
            cost_config.location_id, 
            "configurar costos"
        )
        
        # Continuar con lógica de negocio
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
        """AD009: Procesar ventas al por mayor con validación"""
        
        # ✅ Validar acceso a la ubicación de venta
        location = await self._validate_location_access(
            admin, 
            sale_data.location_id, 
            "procesar ventas"
        )
        
        # Validar que es local si es necesario
        if location.type != "local":
            raise HTTPException(400, "Ventas al por mayor solo en locales de venta")
        
        # Continuar con lógica de venta
        try:
            # Crear venta mayorista
            sale_dict = sale_data.dict()
            sale_dict["processed_by_user_id"] = admin.id
            
            db_sale = self.repository.create_wholesale_sale(sale_dict)
            
            return WholesaleSaleResponse(
                id=db_sale.id,
                customer_name=sale_data.customer_name,
                customer_document=sale_data.customer_document,
                customer_phone=sale_data.customer_phone,
                location_id=location.id,
                location_name=location.name,
                total_amount=db_sale.total_amount,
                discount_amount=db_sale.discount_amount,
                final_amount=db_sale.final_amount,
                payment_method=sale_data.payment_method,
                sale_date=db_sale.created_at,
                processed_by_user_id=admin.id,
                processed_by_name=admin.full_name,
                items_count=len(sale_data.items),
                notes=sale_data.notes
            )
            
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Error procesando venta mayorista: {str(e)}")
    
    # ==================== AD010: REPORTES DE VENTAS ====================
    
    async def generate_sales_report(
        self,
        filters: ReportFilter,
        admin: User
    ) -> List[SalesReport]:
        """AD010: Generar reportes con validación de ubicaciones"""
        
        # ✅ Filtrar solo ubicaciones que puede gestionar
        managed_location_ids = await self._filter_managed_locations(
            admin, 
            filters.location_ids
        )
        
        # ✅ Validar usuarios si se especifican
        if filters.user_ids:
            managed_user_ids = await self._get_managed_user_ids(admin)
            invalid_users = set(filters.user_ids) - set(managed_user_ids)
            if invalid_users:
                raise HTTPException(403, f"Sin permisos para usuarios: {list(invalid_users)}")
        
        # Actualizar filtros con datos validados
        filters.location_ids = managed_location_ids
        
        # Generar reportes
        reports = self.repository.generate_sales_reports(filters)
        return reports
    
    # ==================== AD011: ALERTAS DE INVENTARIO ====================
    
    async def configure_inventory_alert(
        self,
        alert_config: InventoryAlert,
        admin: User
    ) -> InventoryAlertResponse:
        """AD011: Configurar alertas con validación"""
        
        # ✅ Validar acceso a la ubicación
        location = await self._validate_location_access(
            admin,
            alert_config.location_id,
            "configurar alertas de inventario"
        )
        
        # Crear alerta
        alert_data = alert_config.dict()
        alert_data["created_by_user_id"] = admin.id
        
        db_alert = self.repository.create_inventory_alert(alert_data)
        
        return InventoryAlertResponse(
            id=db_alert.id,
            location_id=location.id,
            location_name=location.name,
            alert_type=alert_config.alert_type.value,
            threshold_quantity=alert_config.threshold_quantity,
            product_reference=alert_config.product_reference,
            is_active=alert_config.is_active,
            created_by_name=admin.full_name,
            created_at=db_alert.created_at
        )
    
    # ==================== AD012: APROBAR DESCUENTOS ====================
    
    async def approve_discount_request(
        self,
        approval: DiscountApproval,
        admin: User
    ) -> DiscountRequestResponse:
        """AD012: Aprobar descuentos con validación de usuario"""
        
        # Buscar solicitud de descuento
        discount_request = self.db.query(DiscountRequest).filter(
            DiscountRequest.id == approval.request_id
        ).first()
        
        if not discount_request:
            raise HTTPException(404, "Solicitud de descuento no encontrada")
        
        # ✅ Validar que puede gestionar al vendedor solicitante
        seller = await self._validate_user_access(
            admin, 
            discount_request.seller_id, 
            "aprobar descuentos de"
        )
        
        # Actualizar solicitud
        discount_request.status = approval.status
        discount_request.administrator_id = admin.id
        discount_request.reviewed_at = datetime.now()
        discount_request.admin_comments = approval.admin_notes
        
        self.db.commit()
        self.db.refresh(discount_request)
        
        return DiscountRequestResponse(
            id=discount_request.id,
            sale_id=discount_request.sale_id,
            requester_user_id=discount_request.seller_id,
            requester_name=seller.full_name,
            location_id=seller.location_id,
            location_name=seller.location.name if seller.location else None,
            original_amount=discount_request.amount,
            discount_amount=approval.discount_amount if hasattr(approval, 'discount_amount') else discount_request.amount,
            discount_percentage=approval.discount_percentage if hasattr(approval, 'discount_percentage') else None,
            reason=discount_request.reason,
            status=discount_request.status,
            requested_at=discount_request.requested_at,
            approved_by_user_id=admin.id,
            approved_by_name=admin.full_name,
            approved_at=discount_request.reviewed_at,
            admin_notes=discount_request.admin_comments
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
        """AD013: Supervisar traslados con validación"""
        
        # ✅ Obtener solo ubicaciones gestionadas
        managed_location_ids = await self._filter_managed_locations(admin)
        
        if not managed_location_ids:
            return {
                "managed_locations": [],
                "total_transfers": 0,
                "transfers_by_status": {},
                "pending_transfers": [],
                "recent_transfers": []
            }
        
        # Obtener overview de transferencias
        return self.repository.get_transfers_overview(managed_location_ids)
    
    # ==================== AD014: SUPERVISAR PERFORMANCE ====================
    
    async def get_users_performance(
        self, 
        admin: User, 
        start_date: date, 
        end_date: date,
        user_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """AD014: Performance con validación de usuarios"""
        
        # ✅ Obtener solo usuarios gestionados
        if user_ids:
            # Validar que puede gestionar todos los usuarios solicitados
            for user_id in user_ids:
                await self._validate_user_access(admin, user_id, "ver performance de")
        else:
            # Si no especifica, usar todos los gestionados
            user_ids = await self._get_managed_user_ids(admin)
        
        if not user_ids:
            return []
        
        # Obtener performance de usuarios
        return self.repository.get_users_performance(user_ids, start_date, end_date)
    
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
        managed_location_ids = await self._filter_managed_locations(admin)
        managed_user_ids = await self._get_managed_user_ids(admin)

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
    async def get_location_statistics(
        self,
        location_id: int,
        start_date: date,
        end_date: date,
        admin: User
    ) -> Dict[str, Any]:
        """
        Obtener estadísticas de ubicación con validación de permisos
        """
        
        # ✅ Validar que el admin puede gestionar esta ubicación
        location = await self._validate_location_access(
            admin, 
            location_id, 
            "ver estadísticas"
        )
        
        # Validar rango de fechas
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fecha inicio debe ser menor o igual a fecha fin"
            )
        
        # Obtener estadísticas
        stats = self.repository.get_location_stats(location_id, start_date, end_date)
        
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se pudieron obtener estadísticas para {location.name}"
            )
        
        return stats
    
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

    def require_location_access(location_param: str = "location_id", action: str = "gestionar"):
        """
        Decorador para validar automáticamente acceso a ubicaciones
        
        Args:
            location_param: Nombre del parámetro que contiene location_id
            action: Descripción de la acción para el mensaje de error
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                # Buscar el parámetro admin/current_user
                admin = None
                for arg in args:
                    if hasattr(arg, 'role') and hasattr(arg, 'id'):
                        admin = arg
                        break
                
                if not admin:
                    raise HTTPException(500, "Admin user not found in method parameters")
                
                # Buscar location_id en los argumentos
                location_id = None
                
                # Buscar en argumentos posicionales
                for arg in args:
                    if hasattr(arg, location_param):
                        location_id = getattr(arg, location_param)
                        break
                
                # Buscar en kwargs
                if location_id is None and location_param in kwargs:
                    location_id = kwargs[location_param]
                
                # Validar acceso si se encontró location_id
                if location_id:
                    await self._validate_location_access(admin, location_id, action)
                
                # Ejecutar función original
                return await func(self, *args, **kwargs)
            
            return wrapper
        return decorator

def require_location_access(location_param: str = "location_id", action: str = "gestionar"):
    """
    Decorador para validar automáticamente acceso a ubicaciones
    
    Args:
        location_param: Nombre del parámetro que contiene location_id
        action: Descripción de la acción para el mensaje de error
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Buscar el parámetro admin/current_user
            admin = None
            for arg in args:
                if hasattr(arg, 'role') and hasattr(arg, 'id'):
                    admin = arg
                    break
            
            if not admin:
                raise HTTPException(500, "Admin user not found in method parameters")
            
            # Buscar location_id en los argumentos
            location_id = None
            
            # Buscar en argumentos posicionales
            for arg in args:
                if hasattr(arg, location_param):
                    location_id = getattr(arg, location_param)
                    break
            
            # Buscar en kwargs
            if location_id is None and location_param in kwargs:
                location_id = kwargs[location_param]
            
            # Validar acceso si se encontró location_id
            if location_id:
                await self._validate_location_access(admin, location_id, action)
            
            # Ejecutar función original
            return await func(self, *args, **kwargs)
        
        return wrapper
    return decorator