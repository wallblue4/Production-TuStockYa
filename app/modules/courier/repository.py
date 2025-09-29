# app/modules/courier/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text, desc
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date

from app.shared.database.models import (
    TransferRequest, User, Location, Product, TransportIncident
)

class CourierRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def get_available_requests_for_courier(self, courier_id: int) -> List[Dict[str, Any]]:
        """CO001: Obtener solicitudes disponibles para corredor - igual que backend antiguo"""
        # Query compleja como en el backend standalone
        query = text("""
            SELECT tr.*, 
                   sl.name as source_location_name,
                   sl.address as source_address,
                   dl.name as destination_location_name,
                   dl.address as destination_address,
                   wk.first_name as warehouse_keeper_first_name,
                   wk.last_name as warehouse_keeper_last_name,
                   r.first_name as requester_first_name,
                   r.last_name as requester_last_name,
                   p.image_url as product_image,
                   CASE 
                       WHEN tr.original_transfer_id IS NOT NULL THEN 'return'
                       ELSE 'transfer'
                   END as request_type,
                   CASE 
                       WHEN tr.original_transfer_id IS NOT NULL THEN 'DEVOLUCIÓN'
                       ELSE 'TRANSFERENCIA'
                   END as request_display_type
            FROM transfer_requests tr
            JOIN locations sl ON tr.source_location_id = sl.id
            JOIN locations dl ON tr.destination_location_id = dl.id
            LEFT JOIN users wk ON tr.warehouse_keeper_id = wk.id
            JOIN users r ON tr.requester_id = r.id
            LEFT JOIN products p ON tr.sneaker_reference_code = p.reference_code
            WHERE tr.pickup_type = 'corredor'
                AND ((tr.status = 'accepted' AND tr.courier_id IS NULL) 
                     OR tr.courier_id = :courier_id)
                AND tr.status IN ('accepted', 'courier_assigned', 'in_transit')
            ORDER BY 
                CASE WHEN tr.purpose = 'cliente' THEN 1 ELSE 2 END,
                CASE WHEN tr.courier_id = :courier_id THEN 1 ELSE 2 END,
                tr.accepted_at ASC
        """)
        
        results = self.db.execute(query, {"courier_id": courier_id}).fetchall()
        
        requests = []
        for row in results:
            # Determinar acción requerida y estado
            if row.status == 'accepted' and row.courier_id is None:
                action_required = "accept"
                status_description = f"Disponible para aceptar {row.request_display_type}"
                urgency = "high" if row.purpose == 'cliente' else "normal"
            elif row.status == 'accepted' and row.courier_id == courier_id:
                action_required = "pickup"
                status_description = f"Ir a recoger {row.request_display_type}"
                urgency = "medium"
            elif row.status == 'in_transit' and row.courier_id == courier_id:
                action_required = "deliver"
                status_description = f"En tránsito - entregar {row.request_display_type}"
                urgency = "high"
            else:
                action_required = "none"
                status_description = "No disponible"
                urgency = "normal"
            
            # Calcular priority score (tiempo desde aceptación)
            priority_score = 0.0
            if row.accepted_at:
                accepted_time = row.accepted_at
                if isinstance(accepted_time, str):
                    accepted_time = datetime.fromisoformat(accepted_time.replace('Z', '+00:00'))
                time_since_accepted = datetime.now() - accepted_time
                priority_score = time_since_accepted.total_seconds() / 3600  # horas
            
            # Información del producto
            product_image = row.product_image
            if not product_image:
                product_image = f"https://via.placeholder.com/300x200?text={row.brand}+{row.model}"
            
            requests.append({
                'id': row.id,
                'status': row.status,
                'request_type': row.request_type,
                'request_display_type': row.request_display_type,
                'sneaker_reference_code': row.sneaker_reference_code,
                'brand': row.brand,
                'model': row.model,
                'size': row.size,
                'quantity': row.quantity,
                'purpose': row.purpose,
                'courier_id': row.courier_id,
                'action_required': action_required,
                'status_description': status_description,
                'urgency': urgency,
                'priority_score': priority_score,
                'product_image': product_image,
                'transport_info': {
                    'pickup_location': {
                        'name': row.source_location_name,
                        'address': row.source_address or 'Dirección no disponible',
                        'contact': f"{row.warehouse_keeper_first_name or ''} {row.warehouse_keeper_last_name or ''}".strip()
                    },
                    'delivery_location': {
                        'name': row.destination_location_name,
                        'address': row.destination_address or 'Dirección no disponible',
                        'contact': f"{row.requester_first_name} {row.requester_last_name}"
                    },
                    'route_context': "DEVOLUCIÓN: Producto regresa al origen" if row.request_type == 'return' else "TRANSFERENCIA: Producto va al destino"
                },
                'request_info': {
                    'pickup_location': row.source_location_name,
                    'pickup_address': row.source_address,
                    'delivery_location': row.destination_location_name,
                    'delivery_address': row.destination_address,
                    'product_description': f"{row.brand} {row.model} - Talla {row.size}",
                    'urgency': "Cliente presente" if row.purpose == 'cliente' else "Restock"
                }
            })
        
        return requests
    
    def accept_courier_request(self, request_id: int, courier_id: int, estimated_time: int, notes: str) -> bool:
        """CO002: Aceptar solicitud como corredor con concurrencia"""
        try:
            # Verificar que la solicitud está disponible (prevenir race conditions)
            transfer = self.db.query(TransferRequest).filter(
                and_(
                    TransferRequest.id == request_id,
                    TransferRequest.status == 'accepted',
                    TransferRequest.courier_id == None
                )
            ).first()
            
            if not transfer:
                return False
            
            # Asignar corredor
            transfer.courier_id = courier_id
            transfer.status = 'courier_assigned'
            transfer.courier_accepted_at = datetime.now()
            transfer.estimated_pickup_time = estimated_time
            transfer.courier_notes = notes
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error aceptando solicitud: {e}")
            return False
    
    def confirm_pickup(self, request_id: int, courier_id: int, pickup_notes: str) -> bool:
        """CO003: Confirmar recolección"""
        try:
            transfer = self.db.query(TransferRequest).filter(
                and_(
                    TransferRequest.id == request_id,
                    TransferRequest.courier_id == courier_id,
                    TransferRequest.status == 'courier_assigned'
                )
            ).first()
            
            if not transfer:
                return False
            
            transfer.status = 'in_transit'
            transfer.picked_up_at = datetime.now()
            transfer.pickup_notes = pickup_notes
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error confirmando pickup: {e}")
            return False
    
    def confirm_delivery(self, request_id: int, courier_id: int, delivery_successful: bool, notes: str) -> bool:
        """CO004: Confirmar entrega"""
        try:
            transfer = self.db.query(TransferRequest).filter(
                and_(
                    TransferRequest.id == request_id,
                    TransferRequest.courier_id == courier_id,
                    TransferRequest.status == 'in_transit'
                )
            ).first()
            
            if not transfer:
                return False
            
            if delivery_successful:
                transfer.status = 'delivered'
                transfer.delivered_at = datetime.now()
            else:
                transfer.status = 'delivery_failed'
                transfer.notes = f"Problema en entrega: {notes}"
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error confirmando entrega: {e}")
            return False
    
    def report_incident(self, request_id: int, courier_id: int, incident_type: str, description: str) -> int:
        """CO005: Reportar incidencia durante transporte"""
        try:
            incident = TransportIncident(
                transfer_request_id=request_id,
                courier_id=courier_id,
                incident_type=incident_type,
                description=description,
                reported_at=datetime.now(),
                resolved=False
            )
            
            self.db.add(incident)
            self.db.commit()
            self.db.refresh(incident)
            
            return incident.id
            
        except Exception as e:
            self.db.rollback()
            print(f"Error reportando incidencia: {e}")
            return 0
    
    def get_my_transports(self, courier_id: int) -> List[Dict[str, Any]]:
        """Obtener transportes asignados al corredor"""
        transports = self.db.query(TransferRequest).filter(
            TransferRequest.courier_id == courier_id
        ).order_by(desc(TransferRequest.courier_accepted_at)).all()
        
        return [
            {
                'id': transport.id,
                'status': transport.status,
                'sneaker_reference_code': transport.sneaker_reference_code,
                'brand': transport.brand,
                'model': transport.model,
                'size': transport.size,
                'quantity': transport.quantity,
                'purpose': transport.purpose,
                'courier_accepted_at': transport.courier_accepted_at.isoformat() if transport.courier_accepted_at else None,
                'picked_up_at': transport.picked_up_at.isoformat() if transport.picked_up_at else None,
                'delivered_at': transport.delivered_at.isoformat() if transport.delivered_at else None,
                'estimated_pickup_time': transport.estimated_pickup_time,
                'courier_notes': transport.courier_notes,
                'pickup_notes': transport.pickup_notes
            }
            for transport in transports
        ]
    
    def get_delivery_history_today(self, courier_id: int) -> List[Dict[str, Any]]:
        """CO006: Obtener historial de entregas del día"""
        today = date.today()
        
        deliveries = self.db.query(TransferRequest).filter(
            and_(
                TransferRequest.courier_id == courier_id,
                TransferRequest.status.in_(['delivered', 'completed', 'delivery_failed']),
                func.date(TransferRequest.delivered_at) == today
            )
        ).order_by(desc(TransferRequest.delivered_at)).all()
        
        return [
            {
                'id': delivery.id,
                'status': delivery.status,
                'sneaker_reference_code': delivery.sneaker_reference_code,
                'brand': delivery.brand,
                'model': delivery.model,
                'size': delivery.size,
                'quantity': delivery.quantity,
                'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                'delivery_successful': delivery.status in ['delivered', 'completed'],
                'notes': delivery.notes
            }
            for delivery in deliveries
        ]