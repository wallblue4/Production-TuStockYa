# app/modules/admin/service.py
import json
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any , Callable, Union , Tuple
from fastapi import HTTPException, status ,UploadFile
from sqlalchemy import func 
from sqlalchemy.orm import Session
from decimal import Decimal
from app.shared.services.video_microservice_client import VideoMicroserviceClient
from functools import wraps
import uuid
import httpx
import os
import logging

from fastapi import APIRouter, Depends, Query, File, UploadFile, Form
from app.shared.services.cloudinary_service import cloudinary_service


from app.config.settings import settings
from .repository import AdminRepository
from .schemas import *

from app.shared.database.models import User, Location ,AdminLocationAssignment , Product ,InventoryChange ,DiscountRequest , VideoProcessingJob ,ProductSize

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        from sqlalchemy import func
        
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
                
                new_location_id = update_dict["location_id"]
                
                # 1. Desactivar TODAS las asignaciones activas del usuario
                self.db.query(UserLocationAssignment)\
                    .filter(
                        UserLocationAssignment.user_id == user_id,
                        UserLocationAssignment.is_active == True
                    ).update({"is_active": False})
                
                # 2. Buscar si ya existe una asignación para esta ubicación específica
                existing_assignment = self.db.query(UserLocationAssignment)\
                    .filter(
                        UserLocationAssignment.user_id == user_id,
                        UserLocationAssignment.location_id == new_location_id
                    ).first()
                
                if existing_assignment:
                    # 2a. Ya existe: reactivarla y actualizar datos
                    existing_assignment.is_active = True
                    existing_assignment.role_at_location = user.role
                    existing_assignment.assigned_at = func.current_timestamp()
                else:
                    # 2b. No existe: crear nueva asignación
                    new_assignment = UserLocationAssignment(
                        user_id=user_id,
                        location_id=new_location_id,
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
        Obtener solicitudes de descuento pendientes de aprobación con validación
        """
        
        # ✅ Obtener solicitudes de usuarios que el admin puede gestionar
        managed_user_ids = await self._get_managed_user_ids(admin)
        
        if not managed_user_ids:
            return []
        
        # Filtrar solicitudes solo de usuarios gestionados
        requests = self.db.query(DiscountRequest)\
            .filter(
                DiscountRequest.seller_id.in_(managed_user_ids),
                DiscountRequest.status == "pending"
            )\
            .order_by(DiscountRequest.requested_at)\
            .all()
        
        discount_responses = []
        for req in requests:
            # Obtener información del vendedor
            seller = self.db.query(User).filter(User.id == req.seller_id).first()
            
            discount_responses.append(DiscountRequestResponse(
                id=req.id,
                requester_user_id=req.seller_id,
                requester_name=seller.full_name if seller else "Usuario desconocido",
                location_id=seller.location_id if seller else None,
                location_name=seller.location.name if seller and seller.location else None,
                original_amount=req.amount,  
                discount_amount=req.amount,   # Mismo valor que el monto solicitado
                discount_percentage=None,     # No calculado en este modelo
                reason=req.reason,
                status=req.status,
                requested_at=req.requested_at,
                approved_by_user_id=None,     # Aún no aprobado
                approved_by_name=None,        # Aún no aprobado  
                approved_at=None,             # Aún no aprobado
                admin_notes=None              # Aún no hay notas
            ))
        
        return discount_responses
    
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
        video_entry: VideoProductEntryWithSizes,
        video_file: UploadFile, 
        reference_image: Optional[UploadFile],
        admin: User
    ) -> ProductCreationResponse:
        """
        AD016: Procesamiento de video con IA + tallas específicas + imagen de referencia
        """

        start_time = datetime.now()
        image_url = None

        if reference_image:
            logger.info(f"📸 SERVICIO - La imagen de referencia llegó al servicio. Nombre: {reference_image.filename}")

            # ==================== SUBIR IMAGEN DE REFERENCIA (OPCIONAL) ====================
            logger.info("PROCESANDO IMAGEN DE REFERENCIA...")

            try:
                logger.info("CloudinaryService importado en método")

                # ... lógica de subida a Cloudinary
                image_url = await cloudinary_service.upload_product_reference_image(
                    reference_image, 
                    temp_reference, 
                    admin.id
                )

                # 👉 Y ESTE LOGGER DESPUÉS DE LA SUBIDA
                logger.info(f"✅ IMAGEN SUBIDA EXITOSAMENTE. URL: {image_url}")

            except Exception as img_error:
                logger.error(f"❌ ERROR SUBIENDO IMAGEN: {str(img_error)}")
                image_url = None
        try:
            logger.info("CloudinaryService importado correctamente")
        except ImportError as e:
            logger.error(f"Error importando CloudinaryService: {e}")
        
        try:
            logger.info(f"🎬 SERVICIO - Iniciando procesamiento para usuario: {admin.email}")
            
            # ==================== VALIDACIONES INICIALES ====================
            
            from app.shared.database.models import Location
            logger.info("🔄 Importando Location...")
            
            warehouse = self.db.query(Location).filter(
                Location.id == video_entry.warehouse_location_id,
                Location.type == "bodega"
            ).first()
            
            logger.info(f"🏭 Warehouse query result: {warehouse}")
            
            if not warehouse:
                logger.error(f"❌ Bodega no encontrada: {video_entry.warehouse_location_id}")
                raise HTTPException(status_code=404, detail="Bodega no encontrada")
            
            logger.info(f"✅ Bodega encontrada: {warehouse.name}")
            
            # ==================== SUBIR IMAGEN DE REFERENCIA (OPCIONAL) ====================
            
            if reference_image:
                logger.info("PROCESANDO IMAGEN DE REFERENCIA...")
                logger.info(f"Imagen: {reference_image.filename}, Tamaño: {reference_image.size}")
                
                try:

                    logger.info("CloudinaryService importado en método")
                    
                    # Verificar configuración de Cloudinary
                    if hasattr(settings, 'cloudinary_cloud_name'):
                        logger.info(f"Cloudinary configurado: {settings.cloudinary_cloud_name}")
                    else:
                        logger.error("Cloudinary NO configurado")
                    
                    temp_reference = f"PROD_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{admin.id}"
                    logger.info(f"Referencia temporal: {temp_reference}")
                    
                    image_url = await cloudinary_service.upload_product_reference_image(
                        reference_image, 
                        temp_reference, 
                        admin.id
                    )
                    logger.info(f"IMAGEN SUBIDA EXITOSAMENTE: {image_url}")
                    
                except Exception as img_error:
                    logger.error(f"ERROR SUBIENDO IMAGEN: {type(img_error).__name__}: {str(img_error)}")
                    import traceback
                    logger.error(f"TRACEBACK: {traceback.format_exc()}")
                    image_url = None
            else:
                logger.info("NO HAY IMAGEN DE REFERENCIA PARA PROCESAR")
                image_url = None
            
            # ==================== PROCESAR VIDEO (SIMULADO) ====================
            
            logger.info("Enviando video directamente al microservicio...")

            try:
                ai_result = await self._send_video_to_microservice_direct(
                    video_file, video_entry, 1, admin.id
                )
                logger.info(f"IA real completada: {ai_result}")
                
            except Exception as microservice_error:
                logger.error(f"Error con microservicio: {str(microservice_error)}")
                # Fallback a simulación
                ai_result = {
                    "detected_brand": video_entry.product_brand or "Unknown",
                    "detected_model": video_entry.product_model or "Unknown",
                    "detected_colors": ["Unknown"],
                    "confidence_score": 0.5,
                    "processing_time": 0.1,
                    "fallback_used": True
                }
            
            # ==================== CREAR PRODUCTO ====================
            
            logger.info("🔄 Creando producto...")
            
            
            # Combinar datos del usuario con IA
            final_brand = video_entry.product_brand or ai_result.get('detected_brand', 'Unknown')
            final_model = video_entry.product_model or ai_result.get('detected_model', 'Unknown')
            logger.info(f"💰 Precio unitario: ${video_entry.unit_price}")
            logger.info(f"📦 Precio por caja: ${video_entry.box_price}")
            
            # Generar código de referencia
            reference_code = f"{final_brand[:3].upper()}-{final_model[:4].upper()}-{uuid.uuid4().hex[:6].upper()}"
            
            logger.info(f"📝 Código generado: {reference_code}")
            
            new_product = Product(
                reference_code=reference_code,
                description=f"{final_brand} {final_model}",
                brand=final_brand,
                model=final_model,
                location_name=warehouse.name,
                image_url=image_url,
                total_quantity=video_entry.total_quantity,
                unit_price=video_entry.unit_price,
                box_price=video_entry.box_price or Decimal('0.00'),
                is_active=1,
                created_at=start_time,
                updated_at=start_time
            )
            
            logger.info("🔄 Agregando producto a BD...")
            self.db.add(new_product)
            self.db.flush()  # Para obtener el ID
            
            logger.info(f"✅ Producto creado con ID: {new_product.id}")
            
            # ==================== CREAR TALLAS ====================
            
            logger.info("🔄 Creando tallas...")
            created_sizes = []
            
            for size_entry in video_entry.size_quantities:
                logger.info(f"📏 Creando talla {size_entry.size} con {size_entry.quantity} unidades")
                
                product_size = ProductSize(
                    product_id=new_product.id,
                    size=size_entry.size,
                    quantity=size_entry.quantity,
                    quantity_exhibition=0,
                    location_name=warehouse.name,
                    created_at=start_time,
                    updated_at=start_time
                )
                
                self.db.add(product_size)
                created_sizes.append(size_entry)
            
            logger.info(f"✅ {len(created_sizes)} tallas creadas")
            
            # ==================== CREAR INVENTORY CHANGE ====================
            
            logger.info("🔄 Creando inventory change...")
            
            inventory_change = InventoryChange(
                product_id=new_product.id,
                change_type="video_inventory_creation",
                quantity_before=0,
                quantity_after=video_entry.total_quantity,
                user_id=admin.id,
                notes=f"Inventario creado por admin - Tallas específicas: {len(video_entry.size_quantities)} - {video_entry.notes or ''}",
                created_at=start_time
            )
            
            self.db.add(inventory_change)
            logger.info("✅ Inventory change creado")
            
            # ==================== COMMIT FINAL ====================
            
            logger.info("🔄 Haciendo commit...")
            self.db.commit()
            self.db.refresh(new_product)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"🎉 Procesamiento completado en {processing_time:.2f}s")
            
            # ==================== RESPUESTA ====================
            
            logger.info("🔄 Construyendo respuesta...")
            
            response = ProductCreationResponse(
                success=True,
                product_id=new_product.id,
                reference_code=reference_code,
                image_url=image_url,
                brand=final_brand,
                model=final_model,
                total_quantity=video_entry.total_quantity,
                warehouse_name=warehouse.name,
                sizes_created=created_sizes,
                ai_confidence_score=ai_result.get('confidence_score'),
                ai_detected_info=ai_result,
                created_by_user_id=admin.id,
                created_by_name=admin.full_name,
                created_at=start_time,
                processing_time_seconds=processing_time,
                unit_price=float(new_product.unit_price),  # Para serializar correctamente
                box_price=float(new_product.box_price) if new_product.box_price else None
            )
            
            logger.info("✅ Respuesta construida")
            return response
            
        except HTTPException as he:
            logger.error(f"❌ HTTPException: {he.detail}")
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ ERROR CRÍTICO en servicio: {type(e).__name__}: {str(e)}")
            
            # Capturar traceback completo
            import traceback
            full_traceback = traceback.format_exc()
            logger.error(f"❌ TRACEBACK COMPLETO:\n{full_traceback}")
            
            # Limpiar imagen si se subió
            if image_url and "example.com" not in image_url:
                logger.info("🗑️ Limpiando imagen...")
            
            # Crear mensaje de error más descriptivo
            error_message = f"Error en servicio: {type(e).__name__}"
            if str(e):
                error_message += f" - {str(e)}"
            
            raise HTTPException(
                status_code=500, 
                detail=error_message
            )

# ==================== 🚀 NUEVO MÉTODO: ENVÍO DIRECTO AL MICROSERVICIO ====================

# app/modules/admin/service.py - MÉTODO DIRECTO CORREGIDO

    async def _send_video_to_microservice_direct(
        self, 
        video_file: UploadFile,
        video_entry: VideoProductEntryWithSizes,
        job_db_id: int,
        admin_id: int
    ) -> Dict[str, Any]:
        """
        Enviar video directamente al microservicio sin almacenar localmente
        VERSIÓN CORREGIDA que maneja correctamente el UploadFile
        """
        import httpx
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Enviando video DIRECTO al microservicio: {settings.VIDEO_MICROSERVICE_URL}")
            
            # Verificar configuración
            if not hasattr(settings, 'VIDEO_MICROSERVICE_URL') or not settings.VIDEO_MICROSERVICE_URL:
                raise Exception("VIDEO_MICROSERVICE_URL no está configurada")
            
            # Preparar metadata con tallas específicas
            metadata = {
                "job_db_id": job_db_id,
                "warehouse_id": video_entry.warehouse_location_id,
                "admin_id": admin_id,
                "estimated_quantity": video_entry.total_quantity,
                "product_brand": video_entry.product_brand,
                "product_model": video_entry.product_model,
                "expected_sizes": [sq.dict() for sq in video_entry.size_quantities],
                "size_quantities": [sq.dict() for sq in video_entry.size_quantities],
                "notes": video_entry.notes,
                "processing_mode": "direct_with_training"
            }
            
            logger.info(f"Metadata: {metadata}")
            
            # CLAVE: Leer el contenido una sola vez y reutilizarlo
            await video_file.seek(0)  # Ir al inicio del archivo
            video_content = await video_file.read()
            
            if not video_content:
                raise Exception("El archivo de video está vacío")
            
            logger.info(f"Video leído: {len(video_content)} bytes")
            
            # Preparar para envío - USAR BytesIO para simular archivo
            from io import BytesIO
            video_stream = BytesIO(video_content)
            
            files = {
                "video": (video_file.filename, video_stream, video_file.content_type or "video/mp4")
            }
            
            data = {
                "job_id": job_db_id or 999,
                "callback_url": f"{settings.BASE_URL}/api/v1/admin/admin/video-processing-complete",
                "metadata": json.dumps(metadata)
            }
            
            # Headers de autenticación
            headers = {}
            if hasattr(settings, 'VIDEO_MICROSERVICE_API_KEY') and settings.VIDEO_MICROSERVICE_API_KEY:
                headers["X-API-Key"] = settings.VIDEO_MICROSERVICE_API_KEY
            
            logger.info(f"Headers configurados: {list(headers.keys())}")
            
            # Envío al microservicio
            async with httpx.AsyncClient(timeout=300) as client:
                logger.info("Realizando llamada HTTP...")
                
                response = await client.post(
                    f"{settings.VIDEO_MICROSERVICE_URL}/api/v1/process-video",
                    files=files,
                    data=data,
                    headers=headers
                )
                
                logger.info(f"Respuesta del microservicio: {response.status_code}")
                logger.info(f"Response content: {response.text[:500]}...")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info("Video procesado exitosamente por microservicio")
                    return {
                        "processing_accepted": True,
                        "job_id": job_db_id,
                        "status": result.get("status", "processing"),
                        "detected_brand": result.get("detected_brand", video_entry.product_brand),
                        "detected_model": result.get("detected_model", video_entry.product_model),
                        "confidence_scores": result.get("confidence_scores", {"overall": 0.0}),
                        "microservice_response": result
                    }
                else:
                    error_detail = response.text
                    logger.error(f"Error del microservicio: {response.status_code} - {error_detail}")
                    raise Exception(f"Microservicio error: {response.status_code} - {error_detail}")
                    
        except Exception as e:
            logger.error(f"Error enviando video al microservicio: {str(e)}")
            raise Exception(f"Error comunicando con microservicio de IA: {str(e)}")

    async def _create_final_product_and_inventory(
        self, 
        processing_job: VideoProcessingJob, 
        ai_result: Dict[str, Any], 
        warehouse: Location, 
        admin: User
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Crear producto final e inventory change tras procesamiento exitoso
        """
        from app.shared.database.models import Product, ProductSize, InventoryChange
        import json
        
        try:
            # Crear producto final
            reference_code = ai_result.get("recommended_reference_code") or f"{processing_job.detected_brand[:3].upper()}-{processing_job.detected_model[:4].upper()}-{processing_job.id}"
            
            final_product = Product(
                reference_code=reference_code,
                description=f"{processing_job.detected_brand} {processing_job.detected_model}",
                brand=processing_job.detected_brand,
                model=processing_job.detected_model,
                color_info=", ".join(json.loads(processing_job.detected_colors)) if processing_job.detected_colors else None,
                location_name=warehouse.name,
                total_quantity=processing_job.estimated_quantity,
                is_active=1,
                created_at=datetime.now(),  
                updated_at=datetime.now()

            )
            
            self.db.add(final_product)
            self.db.flush()  # Para obtener el ID
            
            # Crear tallas
            detected_sizes = json.loads(processing_job.detected_sizes) if processing_job.detected_sizes else []
            if detected_sizes:
                quantity_per_size = processing_job.estimated_quantity // len(detected_sizes)
                for size in detected_sizes:
                    product_size = ProductSize(
                        product_id=final_product.id,
                        size=size,
                        quantity=quantity_per_size,
                        location_name=warehouse.name
                    )
                    self.db.add(product_size)
            
            # Crear inventory change final
            inventory_change = InventoryChange(
                product_id=final_product.id,
                change_type="video_ai_creation",
                quantity_before=0,
                quantity_after=processing_job.estimated_quantity,
                user_id=admin.id,
                notes=f"Producto creado via IA - Video: {processing_job.original_filename} - Confianza: {processing_job.confidence_score*100:.1f}%",
                created_at=datetime.now()
            )
            
            self.db.add(inventory_change)
            self.db.flush()
            
            return final_product.id, inventory_change.id
            
        except Exception as e:
            self.db.rollback()
            raise Exception(f"Error creando producto final: {str(e)}")
    
    async def _process_video_with_microservice(
        self, 
        video_path: str, 
        video_entry: VideoProductEntry,
        job_db_id: int,
        admin_id: int
    ) -> Dict[str, Any]:
        """Procesar video con microservicio de IA - VERSIÓN CORREGIDA"""
        try:
            logger.info(f"🔄 Enviando video al microservicio: {settings.VIDEO_MICROSERVICE_URL}")
            monolito_api_key = getattr(settings, 'VIDEO_MICROSERVICE_API_KEY', 'NO_CONFIGURADA')
            logger.info(f"🏢 MONOLITO - Enviando request a: {settings.VIDEO_MICROSERVICE_URL}")
            logger.info(f"🔑 MONOLITO - API Key configurada: {monolito_api_key[:10] + '...' if monolito_api_key and monolito_api_key != 'NO_CONFIGURADA' else 'VACÍA/NO_CONFIGURADA'}")
            
            # ✅ VERIFICAR CONFIGURACIÓN
            if not hasattr(settings, 'VIDEO_MICROSERVICE_URL') or not settings.VIDEO_MICROSERVICE_URL:
                raise Exception("VIDEO_MICROSERVICE_URL no está configurada")
            
            metadata = {
                "job_db_id": job_db_id,
                "warehouse_id": video_entry.warehouse_location_id,
                "admin_id": admin_id,
                "estimated_quantity": video_entry.estimated_quantity,
                "product_brand": video_entry.product_brand,
                "product_model": video_entry.product_model,
                "expected_sizes": video_entry.expected_sizes,
                "notes": video_entry.notes
            }
            
            # ✅ PREPARAR EL ARCHIVO DE VIDEO
            with open(video_path, "rb") as video_file:
                files = {"video": (os.path.basename(video_path), video_file, "video/mp4")}
                data = {
                    "job_id": job_db_id,
                    "callback_url": f"{settings.BASE_URL}/api/v1/admin/admin/video-processing-complete",
                    "metadata": json.dumps(metadata)
                }
                
                # ✅ HEADERS CORRECTOS PARA AUTENTICACIÓN
                headers = {}
                if hasattr(settings, 'VIDEO_MICROSERVICE_API_KEY') and settings.VIDEO_MICROSERVICE_API_KEY:
                    headers["X-API-Key"] = settings.VIDEO_MICROSERVICE_API_KEY  # ⚠️ CAMBIO: X-API-Key en lugar de Authorization
                
                # ✅ LLAMADA AL MICROSERVICIO CON URL CORRECTA
                async with httpx.AsyncClient(timeout=300) as client:
                    response = await client.post(
                        f"{settings.VIDEO_MICROSERVICE_URL}/api/v1/process-video",  # ✅ Variable correcta
                        files=files,
                        data=data,
                        headers=headers
                    )
                    
                    logger.info(f"🔄 Respuesta del microservicio: {response.status_code}")
                    
                    if response.status_code != 200:
                        error_text = response.text
                        logger.error(f"❌ Error en microservicio {response.status_code}: {error_text}")
                        raise Exception(f"Error en microservicio: {response.status_code} - {error_text}")
                    
                    result = response.json()
                    logger.info(f"✅ Video enviado exitosamente - Job ID: {job_db_id}")
                    
                    return {
                        "processing_accepted": True,
                        "job_id": job_db_id,
                        "status": result.get("status", "processing"),
                        "detected_brand": video_entry.product_brand or "Processing...",
                        "detected_model": video_entry.product_model or "Processing...",
                        "confidence_scores": {"overall": 0.0}
                    }
                    
        except httpx.TimeoutException:
            error_msg = f"Timeout procesando video - Job ID: {job_db_id}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except httpx.ConnectError as e:
            error_msg = f"No se pudo conectar al microservicio: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Error procesando video con microservicio: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
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
        Obtener historial de videos procesados - USANDO TABLA DEDICADA
        """
        from app.shared.database.models import VideoProcessingJob, Location, User
        import json
        
        query = self.db.query(VideoProcessingJob, Location, User)\
            .join(Location, VideoProcessingJob.warehouse_location_id == Location.id)\
            .join(User, VideoProcessingJob.processed_by_user_id == User.id)
        
        # Filtros
        if status:
            query = query.filter(VideoProcessingJob.processing_status == status)
        
        if warehouse_id:
            query = query.filter(VideoProcessingJob.warehouse_location_id == warehouse_id)
        
        if date_from:
            query = query.filter(VideoProcessingJob.created_at >= date_from)
        
        if date_to:
            query = query.filter(VideoProcessingJob.created_at <= date_to)
        
        # Ordenar por más recientes primero
        query = query.order_by(VideoProcessingJob.created_at.desc())
        
        records = query.limit(limit).all()
        
        # Construir respuestas
        results = []
        for job, location, user in records:
            results.append(VideoProcessingResponse(
                id=job.id,
                video_file_path=job.video_file_path,
                warehouse_location_id=job.warehouse_location_id,
                warehouse_name=location.name,
                estimated_quantity=job.estimated_quantity,
                processing_status=job.processing_status,
                ai_extracted_info=json.loads(job.ai_results_json) if job.ai_results_json else {},
                detected_products=[{
                    "brand": job.detected_brand,
                    "model": job.detected_model,
                    "colors": json.loads(job.detected_colors) if job.detected_colors else [],
                    "sizes": json.loads(job.detected_sizes) if job.detected_sizes else [],
                    "confidence": float(job.confidence_score) if job.confidence_score else 0.0
                }] if job.processing_status == "completed" else [],
                confidence_score=float(job.confidence_score) if job.confidence_score else 0.0,
                processed_by_user_id=job.processed_by_user_id,
                processed_by_name=user.full_name,
                processing_started_at=job.processing_started_at,
                processing_completed_at=job.processing_completed_at,
                error_message=job.error_message,
                notes=job.notes
            ))
        
        return results
    
    async def _create_products_from_ai_results(
        self, 
        ai_results: Dict[str, Any], 
        processing_job
    ) -> List[Any]:
        """
        Crear productos reales en BD basado en resultados de IA
        """
        from app.shared.database.models import Product, ProductSize
        import json
        
        created_products = []
        
        try:
            # Obtener productos detectados
            detected_products = ai_results.get("detected_products", [])
            
            if not detected_products:
                logger.warning(f"No hay productos detectados para crear - Job {processing_job.id}")
                return created_products
            
            # Usar el mejor producto detectado
            best_product = detected_products[0]
            
            # Generar código de referencia
            reference_code = self._generate_reference_code(
                best_product.get('brand', 'Unknown'),
                best_product.get('model_name', 'Unknown')
            )
            
            # Obtener warehouse
            from app.shared.database.models import Location
            warehouse = self.db.query(Location).filter(
                Location.id == processing_job.warehouse_location_id
            ).first()
            
            # Crear producto
            new_product = Product(
                reference_code=reference_code,
                description=f"{best_product.get('brand', 'Unknown')} {best_product.get('model_name', 'Unknown')}",
                brand=best_product.get('brand', 'Unknown'),
                model=best_product.get('model_name', 'Unknown'), 
                color_info=best_product.get('color', 'Unknown'),
                location_name=warehouse.name if warehouse else "Unknown",
                unit_price=Decimal('0.00'),
                box_price=Decimal('0.00'),
                total_quantity=processing_job.estimated_quantity,
                is_active=1,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            self.db.add(new_product)
            self.db.flush()  # Para obtener ID
            
            # Crear tallas (distribución equitativa)
            sizes = ['7', '8', '9', '10', '11', '12']  # Tallas por defecto
            quantity_per_size = processing_job.estimated_quantity // len(sizes)
            
            for size in sizes:
                product_size = ProductSize(
                    product_id=new_product.id,
                    size=size,
                    quantity=quantity_per_size,
                    quantity_exhibition=0,
                    location_name=warehouse.name if warehouse else "Unknown",
                    created_at=deatetime.now(),
                    updated_at=deatetime.now() 
                )
                self.db.add(product_size)
            
            created_products.append(new_product)
            
            logger.info(f"✅ Producto creado: {reference_code} - {best_product.get('brand')} {best_product.get('model_name')}")
            
            return created_products
            
        except Exception as e:
            logger.error(f"❌ Error creando productos: {e}")
            self.db.rollback()
            raise e

    def _generate_reference_code(self, brand: str, model: str) -> str:
        """Generar código de referencia único"""
        import uuid
        
        brand_code = (brand or "UNK")[:3].upper()
        model_code = (model or "MDL")[:4].upper() 
        unique_suffix = str(uuid.uuid4())[:6].upper()
        
        return f"{brand_code}-{model_code}-{unique_suffix}"

    async def get_video_processing_details(self, video_id: int, admin_user: User) -> VideoProcessingResponse:
        """
        Obtener detalles específicos de video procesado - USANDO TABLA DEDICADA
        """
        from app.shared.database.models import VideoProcessingJob, Location, User
        import json
        
        # Buscar el job específico
        query = self.db.query(VideoProcessingJob, Location, User)\
            .join(Location, VideoProcessingJob.warehouse_location_id == Location.id)\
            .join(User, VideoProcessingJob.processed_by_user_id == User.id)\
            .filter(VideoProcessingJob.id == video_id)
        
        result = query.first()
        
        if not result:
            raise HTTPException(status_code=404, detail="Video no encontrado")
        
        job, location, user = result
        
        # Construir respuesta detallada
        return VideoProcessingResponse(
            id=job.id,
            video_file_path=job.video_file_path,
            warehouse_location_id=job.warehouse_location_id,
            warehouse_name=location.name,
            estimated_quantity=job.estimated_quantity,
            processing_status=job.processing_status,
            ai_extracted_info=json.loads(job.ai_results_json) if job.ai_results_json else {},
            detected_products=[{
                "brand": job.detected_brand,
                "model": job.detected_model,
                "colors": json.loads(job.detected_colors) if job.detected_colors else [],
                "sizes": json.loads(job.detected_sizes) if job.detected_sizes else [],
                "confidence": float(job.confidence_score) if job.confidence_score else 0.0
            }] if job.processing_status == "completed" and job.detected_brand else [],
            confidence_score=float(job.confidence_score) if job.confidence_score else 0.0,
            processed_by_user_id=job.processed_by_user_id,
            processed_by_name=user.full_name,
            processing_started_at=job.processing_started_at,
            processing_completed_at=job.processing_completed_at,
            error_message=job.error_message,
            notes=job.notes
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