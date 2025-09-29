# app/modules/transfers_new/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func, text
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from app.shared.database.models import (
    TransferRequest, User, Location, Product, ProductSize, InventoryChange
)

class TransfersRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create_transfer_request(self, transfer_data: Dict[str, Any], requester_id: int) -> TransferRequest:
        """Crear nueva solicitud de transferencia"""
        transfer = TransferRequest(
            requester_id=requester_id,
            source_location_id=transfer_data['source_location_id'],
            destination_location_id=transfer_data['destination_location_id'],
            sneaker_reference_code=transfer_data['sneaker_reference_code'],
            brand=transfer_data['brand'],
            model=transfer_data['model'],
            size=transfer_data['size'],
            quantity=transfer_data['quantity'],
            purpose=transfer_data['purpose'],
            pickup_type=transfer_data['pickup_type'],
            destination_type=transfer_data.get('destination_type', 'bodega'),
            notes=transfer_data.get('notes'),
            status='pending',
            requested_at=datetime.now()
        )
        
        self.db.add(transfer)
        self.db.commit()
        self.db.refresh(transfer)
        return transfer
    
    def get_transfer_requests_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Obtener solicitudes de transferencia por usuario - igual que backend antiguo"""
        # Query compleja como en el backend standalone
        query = text("""
            SELECT tr.*, 
                   sl.name as source_location_name,
                   dl.name as destination_location_name,
                   c.first_name as courier_first_name, c.last_name as courier_last_name,
                   wk.first_name as warehouse_keeper_first_name, wk.last_name as warehouse_keeper_last_name,
                   CASE 
                       WHEN tr.request_type = 'return' THEN 'Devolución'
                       ELSE 'Transferencia'
                   END as request_display_type,
                   CASE 
                       WHEN tr.request_type = 'return' THEN 'Devolviendo a origen'
                       ELSE 'Enviando a destino'
                   END as workflow_description,
                   orig.id as original_transfer_info,
                   orig.requested_at as original_transfer_date
            FROM transfer_requests tr
            JOIN locations sl ON tr.source_location_id = sl.id
            JOIN locations dl ON tr.destination_location_id = dl.id
            LEFT JOIN users c ON tr.courier_id = c.id
            LEFT JOIN users wk ON tr.warehouse_keeper_id = wk.id
            LEFT JOIN transfer_requests orig ON tr.original_transfer_id = orig.id
            WHERE tr.requester_id = :user_id
            ORDER BY tr.requested_at DESC
        """)
        
        results = self.db.execute(query, {"user_id": user_id}).fetchall()
        
        transfers = []
        for row in results:
            # Calcular tiempo transcurrido
            requested_at = row.requested_at
            if isinstance(requested_at, str):
                requested_at = datetime.fromisoformat(requested_at.replace('Z', '+00:00'))
            
            time_diff = datetime.now() - requested_at
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)
            time_elapsed = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            # Información de estado
            status_info = self._get_transfer_status_info(row.status, row.purpose)
            
            # Determinar prioridad
            priority = 'high' if row.purpose == 'cliente' else 'normal'
            
            transfers.append({
                'id': row.id,
                'status': row.status,
                'sneaker_reference_code': row.sneaker_reference_code,
                'brand': row.brand,
                'model': row.model,
                'size': row.size,
                'quantity': row.quantity,
                'purpose': row.purpose,
                'pickup_type': row.pickup_type,
                'destination_type': row.destination_type or 'bodega',
                'requested_at': requested_at.isoformat(),
                'time_elapsed': time_elapsed,
                'priority': priority,
                'status_info': status_info,
                'location_info': {
                    'from': {
                        'name': row.source_location_name,
                        'address': 'Dirección no disponible'
                    },
                    'to': {
                        'name': row.destination_location_name
                    }
                },
                'participants': {
                    'courier_name': f"{row.courier_first_name} {row.courier_last_name}" if row.courier_first_name else None,
                    'warehouse_keeper_name': f"{row.warehouse_keeper_first_name} {row.warehouse_keeper_last_name}" if row.warehouse_keeper_first_name else None
                },
                'notes': row.notes,
                'is_self_pickup': row.pickup_type == 'vendedor',
                'request_display_type': row.request_display_type,
                'workflow_description': row.workflow_description
            })
        
        return transfers
    
    def _get_transfer_status_info(self, status: str, purpose: str) -> Dict[str, Any]:
        """Obtener información detallada del estado"""
        status_mapping = {
            'pending': {
                'title': 'Solicitud Pendiente',
                'description': 'Esperando que bodeguero acepte la solicitud',
                'detail': 'Tu solicitud está en cola para ser procesada',
                'action_required': 'Esperar confirmación del bodeguero',
                'next_step': 'El bodeguero revisará disponibilidad',
                'urgency': 'high' if purpose == 'cliente' else 'normal',
                'progress_percentage': 10
            },
            'accepted': {
                'title': 'Solicitud Aceptada',
                'description': 'Bodeguero confirmó disponibilidad y está preparando el producto',
                'detail': 'El producto está siendo preparado para envío',
                'action_required': 'Esperar que corredor recoja',
                'next_step': 'Asignación de corredor',
                'urgency': 'medium',
                'progress_percentage': 30
            },
            'in_transit': {
                'title': 'En Tránsito',
                'description': 'Corredor tiene el producto y está en camino',
                'detail': 'El producto está siendo transportado a tu ubicación',
                'action_required': 'Esperar entrega del corredor',
                'next_step': 'Corredor entregará el producto',
                'urgency': 'medium',
                'progress_percentage': 70
            },
            'delivered': {
                'title': 'Producto Entregado',
                'description': 'Corredor entregó el producto',
                'detail': 'Confirma que recibiste el producto en buenas condiciones',
                'action_required': 'Confirmar recepción',
                'next_step': 'Confirmar recepción del producto',
                'urgency': 'high',
                'progress_percentage': 90
            },
            'completed': {
                'title': 'Transferencia Completada',
                'description': 'Proceso completado exitosamente',
                'detail': 'El inventario fue actualizado automáticamente',
                'action_required': None,
                'next_step': 'Transferencia finalizada',
                'urgency': 'normal',
                'progress_percentage': 100
            },
            'cancelled': {
                'title': 'Transferencia Cancelada',
                'description': 'La solicitud fue cancelada',
                'detail': 'La transferencia no se completó',
                'action_required': None,
                'next_step': 'Puede solicitar nuevamente si es necesario',
                'urgency': 'normal',
                'progress_percentage': 0
            }
        }
        
        return status_mapping.get(status, {
            'title': 'Estado Desconocido',
            'description': 'Estado no reconocido',
            'detail': f'Estado actual: {status}',
            'urgency': 'normal',
            'progress_percentage': 0
        })
    
    def get_transfer_summary(self, user_id: int) -> Dict[str, Any]:
        """Obtener resumen de transferencias del usuario"""
        transfers = self.get_transfer_requests_by_user(user_id)
        
        summary = {
            "total_requests": len(transfers),
            "transfers": len([t for t in transfers if t.get('request_display_type') == 'Transferencia']),
            "returns": len([t for t in transfers if t.get('request_display_type') == 'Devolución']),
            "pending": len([t for t in transfers if t['status'] == 'pending']),
            "in_progress": len([t for t in transfers if t['status'] in ['accepted', 'in_transit']]),
            "completed": len([t for t in transfers if t['status'] in ['delivered', 'completed']]),
            "cancelled": len([t for t in transfers if t['status'] == 'cancelled']),
            "awaiting_confirmation": len([t for t in transfers if t['status'] == 'delivered'])
        }
        
        return summary
    
    def confirm_reception(self, transfer_id: int, received_quantity: int, condition_ok: bool, notes: str, user_id: int) -> bool:
        """Confirmar recepción de transferencia con actualización de inventario"""
        try:
            # Obtener transferencia
            transfer = self.db.query(TransferRequest).filter(TransferRequest.id == transfer_id).first()
            if not transfer:
                return False
            
            # Actualizar estado de transferencia
            transfer.status = 'completed'
            transfer.confirmed_reception_at = datetime.now()
            transfer.received_quantity = received_quantity
            transfer.reception_notes = notes
            
            # Actualizar inventario si condición OK
            if condition_ok:
                # Buscar producto destino
                product_size = self.db.query(ProductSize).join(Product).filter(
                    and_(
                        Product.reference_code == transfer.sneaker_reference_code,
                        ProductSize.size == transfer.size,
                        ProductSize.location_name == f"Local #{transfer.destination_location_id}"
                    )
                ).first()
                
                if product_size:
                    # Actualizar cantidad
                    quantity_before = product_size.quantity
                    product_size.quantity += received_quantity
                    
                    # Registrar cambio en historial
                    inventory_change = InventoryChange(
                        product_id=product_size.product_id,
                        change_type='transfer_reception',
                        size=transfer.size,
                        quantity_before=quantity_before,
                        quantity_after=product_size.quantity,
                        user_id=user_id,
                        reference_id=transfer_id,
                        notes=f"Recepción de transferencia #{transfer_id} - {notes}"
                    )
                    self.db.add(inventory_change)
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error confirmando recepción: {e}")
            return False