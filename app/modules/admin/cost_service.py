from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal
from fastapi import HTTPException
import json

from app.shared.database.models import User, Location
from .repository import CostRepository
from .calculator_service import CostCalculatorService
from .schemas import (
    CostConfigurationCreate, CostConfigurationUpdate, CostConfigurationResponse,
    CostPaymentCreate, CostPaymentResponse, CostDashboard, OperationalDashboard,
    DeletionAnalysis, UpdateAmountRequest, CostOperationResponse
)

class CostService:
    """Servicio principal para gestión de costos"""
    
    def __init__(self, db):
        self.db = db
        self.repository = CostRepository(db)
        self.calculator = CostCalculatorService(self.repository)
    
    # ==================== CONFIGURACIONES ====================
    
    async def create_cost_configuration(
        self, 
        cost_config: CostConfigurationCreate, 
        admin: User
    ) -> CostConfigurationResponse:
        """Crear nueva configuración de costo"""
        
        # Validar acceso a la ubicación
        location = await self._validate_location_access(
            admin, cost_config.location_id, "crear costos"
        )
        
        # Verificar si ya existe configuración activa del mismo tipo
        existing_configs = self.repository.get_active_cost_configurations(cost_config.location_id)
        existing_types = {config["cost_type"] for config in existing_configs}
        
        
        # Crear configuración
        cost_data = cost_config.dict()
        result = self.repository.create_cost_configuration(cost_data, admin.id)
        
        # Construir respuesta
        return CostConfigurationResponse(
            id=result["id"],
            location_id=result["location_id"],
            location_name=location.name,
            cost_type=result["cost_type"],
            amount=result["amount"],
            frequency=result["frequency"],
            description=result["description"],
            is_active=result["is_active"],
            start_date=result["start_date"],
            end_date=result["end_date"],
            created_by_user_id=admin.id,
            created_by_name=admin.full_name,
            created_at=result["created_at"],
            updated_at=result["created_at"]
        )
    
    async def update_cost_configuration(
        self,
        cost_id: int,
        cost_update: CostConfigurationUpdate,
        admin: User
    ) -> CostConfigurationResponse:
        """Actualizar configuración existente"""
        
        # Obtener configuración actual
        current_config = self.repository.get_cost_configuration_by_id(cost_id)
        if not current_config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        
        # Validar permisos
        await self._validate_location_access(
            admin, current_config["location_id"], "actualizar costos"
        )
        
        # Aplicar actualización
        update_data = cost_update.dict(exclude_unset=True)
        result = self.repository.update_cost_configuration(cost_id, update_data)
        
        return CostConfigurationResponse(**result)
    
    async def update_cost_amount(
        self,
        cost_id: int,
        update_request: UpdateAmountRequest,
        admin: User
    ) -> CostOperationResponse:
        """Actualizar monto de costo con fecha efectiva"""
        
        # Obtener configuración
        config = self.repository.get_cost_configuration_by_id(cost_id)
        if not config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        
        # Validar permisos
        await self._validate_location_access(admin, config["location_id"], "actualizar costos")
        
        # Verificar que no hay pagos realizados después de la fecha efectiva
        future_payments = self.repository.get_paid_payments_for_config(
            cost_id, update_request.effective_date, date(2030, 12, 31)
        )
        
        if future_payments:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede actualizar: hay {len(future_payments)} pagos realizados después de {update_request.effective_date}"
            )
        
        # Aplicar actualización
        old_amount = config["amount"]
        update_data = {
            "amount": update_request.new_amount,
            "updated_at": datetime.now()
        }
        
        self.repository.update_cost_configuration(cost_id, update_data)
        
        return CostOperationResponse(
            success=True,
            message=f"Monto actualizado de ${old_amount:,.2f} a ${update_request.new_amount:,.2f}",
            data={
                "old_amount": old_amount,
                "new_amount": update_request.new_amount,
                "effective_date": update_request.effective_date,
                "amount_difference": update_request.new_amount - old_amount
            }
        )
    
    async def get_cost_configurations(
        self,
        admin: User,
        location_id: Optional[int] = None,
        cost_type: Optional[str] = None
    ) -> List[CostConfigurationResponse]:
        """Obtener configuraciones con filtros"""
        
        if location_id:
            # Validar acceso a ubicación específica
            await self._validate_location_access(admin, location_id, "ver costos")
            configs = self.repository.get_active_cost_configurations(location_id)
        else:
            # Obtener de todas las ubicaciones gestionadas
            configs = self.repository.get_cost_configurations_by_admin(admin.id)
        
        # Filtrar por tipo si se especifica
        if cost_type:
            configs = [c for c in configs if c["cost_type"] == cost_type]
        
        return [CostConfigurationResponse(**config) for config in configs]
    
    # ==================== PAGOS ====================
    
    async def register_payment(
        self,
        payment_data: CostPaymentCreate,
        admin: User
    ) -> CostPaymentResponse:
        """Registrar pago realizado"""
        
        # Obtener configuración para validar acceso
        config = self.repository.get_cost_configuration_by_id(
            payment_data.cost_configuration_id
        )
        if not config:
            raise HTTPException(status_code=404, detail="Configuración de costo no encontrada")
        
        # Validar permisos
        await self._validate_location_access(admin, config["location_id"], "registrar pagos")
        
        # Verificar que no existe pago duplicado para la misma fecha de vencimiento
        existing_payments = self.repository.get_paid_payments_for_config(
            payment_data.cost_configuration_id,
            payment_data.due_date,
            payment_data.due_date
        )
        
        if existing_payments:
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un pago registrado para la fecha de vencimiento {payment_data.due_date}"
            )
        
        # Registrar pago
        payment_dict = payment_data.dict()
        payment_dict["paid_by_user_id"] = admin.id
        
        result = self.repository.create_payment_record(payment_dict)
        
        return CostPaymentResponse(
            id=result["id"],
            cost_configuration_id=result["cost_configuration_id"],
            due_date=result["due_date"],
            payment_date=result["payment_date"],
            amount=result["amount"],
            payment_method=result["payment_method"],
            payment_reference=result["payment_reference"],
            notes=result["notes"],
            paid_by_user_id=admin.id,
            paid_by_name=admin.full_name,
            created_at=result["created_at"]
        )
    
    # ==================== DASHBOARDS ====================
    
    async def get_location_cost_dashboard(
        self,
        location_id: int,
        admin: User
    ) -> CostDashboard:
        """Obtener dashboard de costos de una ubicación"""
        
        # Validar acceso
        await self._validate_location_access(admin, location_id, "ver dashboard de costos")
        
        # Calcular dashboard dinámicamente
        dashboard_data = self.calculator.calculate_dashboard_data(location_id)
        
        return CostDashboard(**dashboard_data)
    
    async def get_operational_dashboard(self, admin: User) -> OperationalDashboard:
        """Obtener dashboard operativo consolidado"""
        
        dashboard_data = self.calculator.calculate_operational_dashboard(admin.id)
        
        return OperationalDashboard(**dashboard_data)
    
    # ==================== ELIMINACIÓN ====================
    
    async def analyze_deletion_impact(self, cost_id: int, admin: User) -> DeletionAnalysis:
        """Analizar impacto de eliminar una configuración"""
        
        config = self.repository.get_cost_configuration_by_id(cost_id)
        if not config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        
        await self._validate_location_access(admin, config["location_id"], "analizar eliminación")
        
        # Obtener datos para análisis
        paid_payments = self.repository.get_all_paid_payments_for_config(cost_id)
        exceptions = self.repository.get_all_payment_exceptions_for_config(cost_id)
        
        # Calcular vencimientos futuros
        today = date.today()
        future_date = today + timedelta(days=365)
        future_payments = self.calculator.calculate_due_payments(cost_id, today, future_date)
        
        total_paid_amount = sum(Decimal(str(p["amount"])) for p in paid_payments)
        
        return DeletionAnalysis(
            has_payments=len(paid_payments) > 0,
            total_paid_payments=len(paid_payments),
            total_paid_amount=total_paid_amount,
            has_exceptions=len(exceptions) > 0,
            total_exceptions=len(exceptions),
            future_pending_count=len(future_payments),
            deletion_recommendation="deactivate" if len(paid_payments) > 0 else "safe_delete",
            can_delete_safely=len(paid_payments) == 0
        )
    
    async def deactivate_cost_configuration(
        self,
        cost_id: int,
        admin: User,
        end_date: Optional[date] = None
    ) -> CostOperationResponse:
        """Desactivar configuración (recomendado vs eliminar)"""
        
        config = self.repository.get_cost_configuration_by_id(cost_id)
        if not config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        
        await self._validate_location_access(admin, config["location_id"], "desactivar costos")
        
        # Determinar fecha de finalización
        if not end_date:
            end_date = date.today()
        
        # Actualizar configuración
        update_data = {
            "is_active": False,
            "end_date": end_date,
            "updated_at": datetime.now()
        }
        
        self.repository.update_cost_configuration(cost_id, update_data)
        
        return CostOperationResponse(
            success=True,
            message=f"Configuración desactivada. No generará más vencimientos después del {end_date}",
            data={
                "cost_id": cost_id,
                "end_date": end_date,
                "action": "deactivated",
                "existing_payments_preserved": True
            }
        )
    
    async def delete_cost_configuration(
        self,
        cost_id: int,
        admin: User,
        force_delete: bool = False
    ) -> CostOperationResponse:
        """Eliminar configuración con validaciones"""
        
        config = self.repository.get_cost_configuration_by_id(cost_id)
        if not config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        
        await self._validate_location_access(admin, config["location_id"], "eliminar costos")
        
        # Analizar impacto
        analysis = await self.analyze_deletion_impact(cost_id, admin)
        
        if analysis.has_payments and not force_delete:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "No se puede eliminar: existen pagos realizados",
                    "analysis": analysis.dict(),
                    "suggestion": "Use force_delete=true o considere desactivar"
                }
            )
        
        if force_delete and analysis.has_payments:
            # Archivar datos antes de eliminar
            archive_id = await self._archive_cost_data(cost_id, admin.id)
            
            # Eliminar en orden correcto
            self.repository.delete_payment_exceptions_for_config(cost_id)
            self.repository.delete_paid_payments_for_config(cost_id)
            self.repository.delete_cost_configuration(cost_id)
            
            return CostOperationResponse(
                success=True,
                message="Configuración eliminada completamente con archivado de datos",
                data={
                    "cost_id": cost_id,
                    "action": "force_deleted",
                    "archive_id": archive_id,
                    "deleted_payments": analysis.total_paid_payments,
                    "deleted_amount": analysis.total_paid_amount
                },
                warnings=["Esta acción no se puede deshacer"]
            )
        else:
            # Eliminación segura sin pagos
            self.repository.delete_payment_exceptions_for_config(cost_id)
            self.repository.delete_cost_configuration(cost_id)
            
            return CostOperationResponse(
                success=True,
                message="Configuración eliminada exitosamente",
                data={
                    "cost_id": cost_id,
                    "action": "deleted",
                    "data_removed": True
                }
            )
    
    # ==================== MÉTODOS PRIVADOS ====================
    
    async def _validate_location_access(
        self, 
        admin: User, 
        location_id: int, 
        action: str
    ) -> Location:
        """Validar que el administrador tiene acceso a la ubicación"""
        
        # Si es boss, tiene acceso a todo
        if admin.role == "boss":
            location = self.db.query(Location).filter(Location.id == location_id).first()
            if not location:
                raise HTTPException(status_code=404, detail="Ubicación no encontrada")
            return location
        
        # Para administradores, verificar asignación
        managed_locations = self.repository.get_managed_locations_for_admin(admin.id)
        managed_location_ids = {loc["id"] for loc in managed_locations}
        
        if location_id not in managed_location_ids:
            raise HTTPException(
                status_code=403,
                detail=f"No tiene permisos para {action} en esta ubicación"
            )
        
        location = self.db.query(Location).filter(Location.id == location_id).first()
        return location
    
    async def _archive_cost_data(self, cost_id: int, admin_id: int) -> int:
       """Archivar datos antes de eliminación forzada"""
       
       config = self.repository.get_cost_configuration_by_id(cost_id)
       paid_payments = self.repository.get_all_paid_payments_for_config(cost_id)
       exceptions = self.repository.get_all_payment_exceptions_for_config(cost_id)
       
       archive_data = {
           "original_cost_id": cost_id,
           "configuration_data": config,
           "paid_payments_data": paid_payments,
           "exceptions_data": exceptions,
           "deleted_by_user_id": admin_id,
           "deletion_reason": "force_delete_with_payments"
       }
       
       return self.repository.create_deletion_archive_record(archive_data)