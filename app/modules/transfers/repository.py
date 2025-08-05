from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, asc, func, case
from sqlalchemy.exc import SQLAlchemyError

from app.shared.database.models import (
    TransferRequest, User, Location, Product, ProductSize,
    TransportIncident, UserLocationAssignment
)
from app.modules.transfers.schemas import TransferFilters, TransferStatus, Purpose

class TransferRepository:
    
    def __init__(self, db: Session):
        self.db = db
    
    # ===== CRUD BÁSICO =====
    
    def create_transfer_request(self, transfer_data: dict, requester_id: int) -> TransferRequest:
        """Crear nueva solicitud de transferencia"""
        try:
            transfer = TransferRequest(
                requester_id=requester_id,
                **transfer_data,
                requested_at=datetime.utcnow()
            )
            self.db.add(transfer)
            self.db.commit()
            self.db.refresh(transfer)
            return transfer
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e
    
    def get_transfer_by_id(self, transfer_id: int) -> Optional[TransferRequest]:
        """Obtener transferencia por ID con relaciones"""
        return self.db.query(TransferRequest).options(
            joinedload(TransferRequest.requester),
            joinedload(TransferRequest.warehouse_keeper),
            joinedload(TransferRequest.courier),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(TransferRequest.id == transfer_id).first()
    
    def update_transfer_status(self, transfer_id: int, status: str, **kwargs) -> bool:
        """Actualizar estado de transferencia"""
        try:
            update_data = {"status": status}
            
            # Agregar timestamps según el estado
            if status == "accepted" and "warehouse_keeper_id" in kwargs:
                update_data["accepted_at"] = datetime.utcnow()
                update_data["warehouse_keeper_id"] = kwargs["warehouse_keeper_id"]
            elif status == "courier_assigned" and "courier_id" in kwargs:
                update_data["courier_id"] = kwargs["courier_id"]
                update_data["courier_accepted_at"] = datetime.utcnow()
            elif status == "in_transit":
                update_data["picked_up_at"] = datetime.utcnow()
            elif status == "delivered":
                update_data["delivered_at"] = datetime.utcnow()
            elif status == "completed":
                update_data["confirmed_reception_at"] = datetime.utcnow()
            
            # Agregar campos adicionales
            for key, value in kwargs.items():
                if key not in ["warehouse_keeper_id", "courier_id"]:
                    update_data[key] = value
            
            rows_updated = self.db.query(TransferRequest).filter(
                TransferRequest.id == transfer_id
            ).update(update_data)
            
            self.db.commit()
            return rows_updated > 0
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e
    
    # ===== CONSULTAS POR ROL =====
    
    def get_pending_requests_for_warehouse(self, user_id: int) -> List[TransferRequest]:
        """BG001: Obtener solicitudes pendientes para bodeguero"""
        # Obtener ubicaciones asignadas al bodeguero
        assigned_locations = self.db.query(UserLocationAssignment.location_id).filter(
            and_(
                UserLocationAssignment.user_id == user_id,
                UserLocationAssignment.role_at_location == 'bodeguero',
                UserLocationAssignment.is_active == True
            )
        ).subquery()
        
        return self.db.query(TransferRequest).options(
            joinedload(TransferRequest.requester),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(
            and_(
                TransferRequest.status == "pending",
                TransferRequest.source_location_id.in_(assigned_locations)
            )
        ).order_by(
            # Prioridad: cliente primero, luego por hora
            case(
                (TransferRequest.purpose == "cliente", 1),
                else_=2
            ),
            asc(TransferRequest.requested_at)
        ).all()
    
    def get_accepted_requests_by_warehouse_keeper(self, warehouse_keeper_id: int) -> List[TransferRequest]:
        """BG002: Obtener solicitudes aceptadas por bodeguero"""
        return self.db.query(TransferRequest).options(
            joinedload(TransferRequest.requester),
            joinedload(TransferRequest.courier),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(
            and_(
                TransferRequest.warehouse_keeper_id == warehouse_keeper_id,
                TransferRequest.status.in_(["accepted", "courier_assigned", "in_transit"])
            )
        ).order_by(asc(TransferRequest.accepted_at)).all()
    
    def get_available_requests_for_courier(self, courier_id: int) -> List[TransferRequest]:
        """CO001: Obtener solicitudes disponibles para corredor"""
        return self.db.query(TransferRequest).options(
            joinedload(TransferRequest.requester),
            joinedload(TransferRequest.warehouse_keeper),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(
            or_(
                # Disponibles para aceptar
                and_(
                    TransferRequest.status == "accepted",
                    TransferRequest.courier_id == None
                ),
                # Ya asignadas a este corredor
                and_(
                    TransferRequest.courier_id == courier_id,
                    TransferRequest.status.in_(["courier_assigned", "in_transit"])
                )
            )
        ).order_by(
            case(
                (TransferRequest.purpose == "cliente", 1),
                else_=2
            ),
            asc(TransferRequest.accepted_at)
        ).all()
    
    def get_transfers_by_requester(self, requester_id: int, 
                                  status_filter: Optional[List[str]] = None) -> List[TransferRequest]:
        """VE003: Obtener transferencias de un vendedor"""
        query = self.db.query(TransferRequest).options(
            joinedload(TransferRequest.warehouse_keeper),
            joinedload(TransferRequest.courier),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(TransferRequest.requester_id == requester_id)
        
        if status_filter:
            query = query.filter(TransferRequest.status.in_(status_filter))
        
        return query.order_by(desc(TransferRequest.requested_at)).all()
    
    def get_pending_receptions_by_requester(self, requester_id: int) -> List[TransferRequest]:
        """VE008: Obtener entregas pendientes de confirmación"""
        return self.db.query(TransferRequest).options(
            joinedload(TransferRequest.courier),
            joinedload(TransferRequest.source_location)
        ).filter(
            and_(
                TransferRequest.requester_id == requester_id,
                TransferRequest.status == "delivered"
            )
        ).order_by(desc(TransferRequest.delivered_at)).all()
    
    # ===== CONSULTAS DE ESTADO =====
    
    def get_transfers_by_status(self, status: str, 
                               location_ids: Optional[List[int]] = None) -> List[TransferRequest]:
        """Obtener transferencias por estado"""
        query = self.db.query(TransferRequest).options(
            joinedload(TransferRequest.requester),
            joinedload(TransferRequest.warehouse_keeper),
            joinedload(TransferRequest.courier),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(TransferRequest.status == status)
        
        if location_ids:
            query = query.filter(
                or_(
                    TransferRequest.source_location_id.in_(location_ids),
                    TransferRequest.destination_location_id.in_(location_ids)
                )
            )
        
        return query.order_by(desc(TransferRequest.requested_at)).all()
    
    def check_product_availability(self, reference_code: str, size: str, 
                                  location_id: int) -> Dict[str, Any]:
        """Verificar disponibilidad de producto"""
        # Buscar producto en la ubicación específica
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return {"available": False, "error": "Location not found"}
        
        product_size = self.db.query(ProductSize).join(Product).filter(
            and_(
                Product.reference_code == reference_code,
                Product.location_name == location.name,
                ProductSize.size == size,
                Product.is_active == 1
            )
        ).first()
        
        if not product_size:
            return {"available": False, "physical_stock": 0}
        
        # Calcular stock reservado (esto debería integrarse con el sistema de reservas)
        physical_stock = product_size.quantity or 0
        
        return {
            "available": physical_stock > 0,
            "physical_stock": physical_stock,
            "available_stock": physical_stock,  # Sin reservas por ahora
            "location_name": location.name
        }
    
    # ===== ESTADÍSTICAS Y MÉTRICAS =====
    
    def get_transfer_summary_by_user(self, user_id: int, role: str) -> Dict[str, int]:
        """Obtener resumen de transferencias por usuario y rol"""
        base_query = self.db.query(TransferRequest)
        
        # Filtrar según el rol
        if role == "vendedor":
            base_query = base_query.filter(TransferRequest.requester_id == user_id)
        elif role == "bodeguero":
            base_query = base_query.filter(TransferRequest.warehouse_keeper_id == user_id)
        elif role == "corredor":
            base_query = base_query.filter(TransferRequest.courier_id == user_id)
        
        # Contar por estado
        status_counts = base_query.with_entities(
            TransferRequest.status,
            func.count(TransferRequest.id).label('count')
        ).group_by(TransferRequest.status).all()
        
        summary = {
            "total_requests": sum(count for _, count in status_counts),
            "pending": 0,
            "accepted": 0,
            "in_transit": 0,
            "delivered": 0,
            "completed": 0,
            "cancelled": 0
        }
        
        for status, count in status_counts:
            if status in summary:
                summary[status] = count
        
        return summary
    
    def get_daily_transfer_metrics(self, date: datetime) -> Dict[str, Any]:
        """Obtener métricas de transferencias del día"""
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
        
        daily_transfers = self.db.query(TransferRequest).filter(
            and_(
                TransferRequest.requested_at >= start_date,
                TransferRequest.requested_at < end_date
            )
        )
        
        total = daily_transfers.count()
        completed = daily_transfers.filter(TransferRequest.status == "completed").count()
        urgent = daily_transfers.filter(TransferRequest.purpose == "cliente").count()
        
        # Tiempo promedio de procesamiento (solo completadas)
        avg_time_query = self.db.query(
            func.avg(
                func.extract('epoch', TransferRequest.confirmed_reception_at) - 
                func.extract('epoch', TransferRequest.requested_at)
            ).label('avg_seconds')
        ).filter(
            and_(
                TransferRequest.confirmed_reception_at.isnot(None),
                TransferRequest.requested_at >= start_date,
                TransferRequest.requested_at < end_date
            )
        ).scalar()
        
        avg_hours = (avg_time_query / 3600) if avg_time_query else 0
        
        return {
            "total_requests": total,
            "completed_requests": completed,
            "urgent_requests": urgent,
            "completion_rate": (completed / total * 100) if total > 0 else 0,
            "average_processing_hours": round(avg_hours, 2)
        }
    
    # ===== VALIDACIONES =====
    
    def can_user_access_transfer(self, transfer_id: int, user_id: int, role: str) -> bool:
        """Verificar si un usuario puede acceder a una transferencia"""
        transfer = self.db.query(TransferRequest).filter(
            TransferRequest.id == transfer_id
        ).first()
        
        if not transfer:
            return False
        
        # Verificar permisos según el rol
        if role == "vendedor":
            return transfer.requester_id == user_id
        elif role == "bodeguero":
            return transfer.warehouse_keeper_id == user_id or transfer.warehouse_keeper_id is None
        elif role == "corredor":
            return transfer.courier_id == user_id or transfer.courier_id is None
        elif role in ["administrador", "boss"]:
            return True
        
        return False
    
    def can_cancel_transfer(self, transfer_id: int, user_id: int) -> bool:
        """Verificar si se puede cancelar una transferencia"""
        transfer = self.db.query(TransferRequest).filter(
            TransferRequest.id == transfer_id
        ).first()
        
        if not transfer:
            return False
        
        # Solo se puede cancelar si está pending o accepted y es el solicitante
        return (
            transfer.requester_id == user_id and 
            transfer.status in ["pending", "accepted"]
        )
    
    # ===== INCIDENCIAS =====
    
    def create_transport_incident(self, transfer_id: int, courier_id: int, 
                                incident_data: dict) -> Optional[int]:
        """Crear incidencia de transporte"""
        try:
            incident = TransportIncident(
                transfer_request_id=transfer_id,
                courier_id=courier_id,
                reported_at=datetime.utcnow(),
                **incident_data
            )
            self.db.add(incident)
            self.db.commit()
            self.db.refresh(incident)
            return incident.id
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e
    
    def get_courier_delivery_history(self, courier_id: int, 
                                   limit: int = 50) -> List[TransferRequest]:
        """Obtener historial de entregas del corredor"""
        return self.db.query(TransferRequest).options(
            joinedload(TransferRequest.requester),
            joinedload(TransferRequest.source_location),
            joinedload(TransferRequest.destination_location)
        ).filter(
            TransferRequest.courier_id == courier_id
        ).order_by(
            desc(TransferRequest.delivered_at),
            desc(TransferRequest.picked_up_at)
        ).limit(limit).all()