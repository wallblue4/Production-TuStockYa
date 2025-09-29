# app/modules/warehouse_new/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text, desc
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.shared.database.models import (
    TransferRequest, User, Location, Product, ProductSize, 
    InventoryChange, UserLocationAssignment
)

class WarehouseRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_managed_locations(self, user_id: int, role: str = 'bodeguero') -> List[Dict[str, Any]]:
        """Obtener ubicaciones gestionadas por el bodeguero"""
        assignments = self.db.query(UserLocationAssignment).join(Location).filter(
            and_(
                UserLocationAssignment.user_id == user_id,
                UserLocationAssignment.role_at_location == role,
                UserLocationAssignment.is_active == True
            )
        ).all()
        
        return [
            {
                'location_id': assignment.location_id,
                'location_name': assignment.location.name,
                'location_type': assignment.location.type,
                'address': assignment.location.address
            }
            for assignment in assignments
        ]
    
    def get_pending_requests_for_warehouse(self, user_id: int) -> List[Dict[str, Any]]:
        """BG001: Obtener solicitudes pendientes - igual que backend antiguo"""
        managed_locations = self.get_user_managed_locations(user_id)
        location_ids = [loc['location_id'] for loc in managed_locations]
        
        if not location_ids:
            return []
        
        # Query compleja igual que en backend antiguo
        query = text("""
            SELECT tr.*, 
                   u.first_name as requester_first_name,
                   u.last_name as requester_last_name,
                   sl.name as source_location_name,
                   sl.address as source_address,
                   dl.name as destination_location_name,
                   dl.address as destination_address,
                   p.image_url as product_image,
                   p.unit_price as product_unit_price,
                   p.box_price as product_box_price,
                   ps.quantity as available_stock,
                   CASE 
                       WHEN tr.request_type = 'return' THEN 'return'
                       ELSE 'transfer'
                   END as request_type
            FROM transfer_requests tr
            JOIN users u ON tr.requester_id = u.id
            JOIN locations sl ON tr.source_location_id = sl.id
            JOIN locations dl ON tr.destination_location_id = dl.id
            LEFT JOIN products p ON tr.sneaker_reference_code = p.reference_code
            LEFT JOIN product_sizes ps ON p.id = ps.product_id 
                AND ps.size = tr.size 
                AND ps.location_name = sl.name
            WHERE tr.status = 'pending' 
                AND tr.source_location_id = ANY(:location_ids)
            ORDER BY 
                CASE WHEN tr.purpose = 'cliente' THEN 1 ELSE 2 END,
                tr.requested_at ASC
        """)
        
        results = self.db.execute(query, {"location_ids": location_ids}).fetchall()
        
        requests = []
        for row in results:
            # Calcular tiempo transcurrido
            requested_at = row.requested_at
            if isinstance(requested_at, str):
                requested_at = datetime.fromisoformat(requested_at.replace('Z', '+00:00'))
            
            time_diff = datetime.now() - requested_at
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)
            time_elapsed = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            # Determinar urgencia
            urgent_action = (
                row.purpose == 'cliente' or 
                row.request_type == 'return' or 
                time_diff > timedelta(hours=2)
            )
            
            priority_level = 'urgent' if urgent_action else 'normal'
            
            requests.append({
                'id': row.id,
                'status': row.status,
                'request_type': row.request_type,
                'sneaker_reference_code': row.sneaker_reference_code,
                'brand': row.brand,
                'model': row.model,
                'size': row.size,
                'quantity': row.quantity,
                'purpose': row.purpose,
                'requester_name': f"{row.requester_first_name} {row.requester_last_name}",
                'location_info': {
                    'source': {
                        'name': row.source_location_name,
                        'address': row.source_address or 'Dirección no disponible'
                    },
                    'destination': {
                        'name': row.destination_location_name,
                        'address': row.destination_address or 'Dirección no disponible'
                    }
                },
                'product_info': {
                    'image_url': row.product_image,
                    'unit_price': float(row.product_unit_price) if row.product_unit_price else 0.0,
                    'box_price': float(row.product_box_price) if row.product_box_price else 0.0,
                    'available_stock': row.available_stock or 0,
                    'sufficient_stock': (row.available_stock or 0) >= row.quantity,
                    'description': f"{row.brand} {row.model} - Talla {row.size}"
                },
                'requested_at': requested_at.isoformat(),
                'time_elapsed': time_elapsed,
                'urgent_action': urgent_action,
                'priority_level': priority_level,
                'estimated_pickup_time': '15-30 minutos'
            })
        
        return requests
    
    def accept_transfer_request(self, request_id: int, acceptance_data: Dict[str, Any], warehouse_keeper_id: int) -> bool:
        """BG002: Aceptar/rechazar solicitud"""
        try:
            transfer = self.db.query(TransferRequest).filter(TransferRequest.id == request_id).first()
            if not transfer:
                return False
            
            if acceptance_data['accepted']:
                transfer.status = 'accepted'
                transfer.warehouse_keeper_id = warehouse_keeper_id
                transfer.accepted_at = datetime.now()
                transfer.notes = acceptance_data.get('warehouse_notes', transfer.notes)
            else:
                transfer.status = 'rejected'
                transfer.notes = f"Rechazado: {acceptance_data.get('rejection_reason', 'Sin razón especificada')}"
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error aceptando solicitud: {e}")
            return False
    
    def get_accepted_requests_by_warehouse_keeper(self, warehouse_keeper_id: int) -> List[Dict[str, Any]]:
        """BG002: Obtener solicitudes aceptadas por bodeguero"""
        query = text("""
            SELECT tr.*, 
                   u.first_name as requester_first_name,
                   u.last_name as requester_last_name,
                   c.first_name as courier_first_name,
                   c.last_name as courier_last_name,
                   sl.name as source_location_name,
                   dl.name as destination_location_name,
                   p.image_url as product_image,
                   p.unit_price as product_unit_price
            FROM transfer_requests tr
            JOIN users u ON tr.requester_id = u.id
            LEFT JOIN users c ON tr.courier_id = c.id
            JOIN locations sl ON tr.source_location_id = sl.id
            JOIN locations dl ON tr.destination_location_id = dl.id
            LEFT JOIN products p ON tr.sneaker_reference_code = p.reference_code
            WHERE tr.warehouse_keeper_id = :warehouse_keeper_id 
                AND tr.status IN ('accepted', 'courier_assigned', 'in_transit')
            ORDER BY tr.accepted_at DESC
        """)
        
        results = self.db.execute(query, {"warehouse_keeper_id": warehouse_keeper_id}).fetchall()
        
        requests = []
        for row in results:
            requests.append({
                'id': row.id,
                'status': row.status,
                'sneaker_reference_code': row.sneaker_reference_code,
                'brand': row.brand,
                'model': row.model,
                'size': row.size,
                'quantity': row.quantity,
                'purpose': row.purpose,
                'requester_name': f"{row.requester_first_name} {row.requester_last_name}",
                'courier_name': f"{row.courier_first_name} {row.courier_last_name}" if row.courier_first_name else "No asignado",
                'courier_assigned': row.courier_id is not None,
                'location_info': {
                    'source': row.source_location_name,
                    'destination': row.destination_location_name
                },
                'product_info': {
                    'image_url': row.product_image,
                    'unit_price': float(row.product_unit_price) if row.product_unit_price else 0.0,
                    'description': f"{row.brand} {row.model} - Talla {row.size}"
                },
                'accepted_at': row.accepted_at.isoformat() if row.accepted_at else None,
                'next_action': 'Esperando corredor' if not row.courier_id else 'Listo para entrega'
            })
        
        return requests
    
    def deliver_to_courier(self, request_id: int, delivery_data: Dict[str, Any]) -> bool:
        """BG003: Entregar producto a corredor con descuento automático de inventario"""
        try:
            transfer = self.db.query(TransferRequest).filter(TransferRequest.id == request_id).first()
            if not transfer:
                return False
            
            # Actualizar estado de transferencia
            transfer.status = 'in_transit'
            transfer.picked_up_at = datetime.now()
            transfer.pickup_notes = delivery_data.get('delivery_notes')
            
            # CRÍTICO: Descuento automático de inventario (requerimiento BG003)
            product_size = self.db.query(ProductSize).join(Product).filter(
                and_(
                    Product.reference_code == transfer.sneaker_reference_code,
                    ProductSize.size == transfer.size,
                    ProductSize.location_name == f"Local #{transfer.source_location_id}"
                )
            ).first()
            
            if product_size and product_size.quantity >= transfer.quantity:
                # Descontar inventario
                quantity_before = product_size.quantity
                product_size.quantity -= transfer.quantity
                
                # Registrar cambio en historial
                inventory_change = InventoryChange(
                    product_id=product_size.product_id,
                    change_type='transfer_pickup',
                    size=transfer.size,
                    quantity_before=quantity_before,
                    quantity_after=product_size.quantity,
                    user_id=transfer.warehouse_keeper_id,
                    reference_id=transfer.id,
                    notes=f"Entrega a corredor - Transferencia #{transfer.id}"
                )
                self.db.add(inventory_change)
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error entregando a corredor: {e}")
            return False
    
    def get_inventory_by_location(self, location_id: int) -> List[Dict[str, Any]]:
        """BG006: Consultar inventario por ubicación"""
        inventory = self.db.query(
            Product.reference_code,
            Product.brand,
            Product.model,
            Product.description,
            Product.unit_price,
            Product.box_price,
            Product.image_url,
            ProductSize.size,
            ProductSize.quantity,
            ProductSize.quantity_exhibition
        ).join(ProductSize).filter(
            ProductSize.location_name == f"Local #{location_id}"
        ).order_by(Product.brand, Product.model, ProductSize.size).all()
        
        return [
            {
                'reference_code': item.reference_code,
                'brand': item.brand,
                'model': item.model,
                'description': item.description,
                'size': item.size,
                'quantity': item.quantity,
                'quantity_exhibition': item.quantity_exhibition,
                'unit_price': float(item.unit_price),
                'box_price': float(item.box_price),
                'image_url': item.image_url,
                'total_value': float(item.quantity * item.unit_price),
                'stock_status': 'Disponible' if item.quantity > 0 else 'Agotado'
            }
            for item in inventory
        ]