# app/modules/warehouse_new/service.py
from typing import Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .repository import WarehouseRepository
from .schemas import (
    WarehouseRequestAcceptance, CourierDelivery, 
    PendingRequestsResponse, AcceptedRequestsResponse, InventoryByLocationResponse
)

class WarehouseService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = WarehouseRepository(db)
    
    async def get_pending_requests(self, user_id: int, user_info: Dict[str, Any]) -> PendingRequestsResponse:
        """BG001: Obtener solicitudes pendientes para bodeguero"""
        requests = self.repository.get_pending_requests_for_warehouse(user_id)
        
        # Estadísticas como en backend antiguo
        breakdown = {
            "total": len(requests),
            "transfers": len([r for r in requests if r['request_type'] == 'transfer']),
            "returns": len([r for r in requests if r['request_type'] == 'return']),
            "urgent_returns": len([r for r in requests if r['request_type'] == 'return']),
            "high_priority": len([r for r in requests if r['urgent_action']])
        }
        
        return PendingRequestsResponse(
            success=True,
            message="Vista unificada: transferencias y devoluciones usan el mismo flujo de procesamiento",
            pending_requests=requests,
            count=len(requests),
            breakdown=breakdown,
            warehouse_keeper=f"{user_info['first_name']} {user_info['last_name']}"
        )
    
    async def accept_request(self, acceptance: WarehouseRequestAcceptance, warehouse_keeper_id: int) -> Dict[str, Any]:
        """BG002: Aceptar/rechazar solicitud de transferencia"""
        
        # Validar que la solicitud existe y está pendiente
        managed_locations = self.repository.get_user_managed_locations(warehouse_keeper_id)
        location_ids = [loc['location_id'] for loc in managed_locations]
        
        if not location_ids:
            raise HTTPException(status_code=403, detail="No tienes ubicaciones asignadas")
        
        acceptance_data = {
            'accepted': acceptance.accepted,
            'rejection_reason': acceptance.rejection_reason,
            'warehouse_notes': acceptance.warehouse_notes
        }
        
        success = self.repository.accept_transfer_request(
            acceptance.transfer_request_id, acceptance_data, warehouse_keeper_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada o no autorizada")
        
        return {
            "success": True,
            "message": "Solicitud aceptada - Disponible para corredores" if acceptance.accepted else "Solicitud rechazada",
            "request_id": acceptance.transfer_request_id,
            "status": "accepted" if acceptance.accepted else "rejected",
            "next_step": "Esperando asignación de corredor" if acceptance.accepted else "Solicitud finalizada"
        }
    
    async def get_accepted_requests(self, warehouse_keeper_id: int, user_info: Dict[str, Any]) -> AcceptedRequestsResponse:
        """BG002: Obtener solicitudes aceptadas y en preparación"""
        requests = self.repository.get_accepted_requests_by_warehouse_keeper(warehouse_keeper_id)
        
        return AcceptedRequestsResponse(
            success=True,
            message="Solicitudes aceptadas y en preparación",
            accepted_requests=requests,
            count=len(requests),
            warehouse_info={
                "warehouse_keeper": f"{user_info['first_name']} {user_info['last_name']}",
                "location_assignments": len(self.repository.get_user_managed_locations(warehouse_keeper_id))
            }
        )
    
    async def deliver_to_courier(self, delivery: CourierDelivery, warehouse_keeper_id: int) -> Dict[str, Any]:
        """BG003: Entregar productos a corredor con descuento automático de inventario"""
        
        delivery_data = {
            'courier_id': delivery.courier_id,
            'delivery_notes': delivery.delivery_notes
        }
        
        success = self.repository.deliver_to_courier(delivery.transfer_request_id, delivery_data)
        
        if not success:
            raise HTTPException(status_code=404, detail="Transferencia no encontrada")
        
        return {
            "success": True,
            "message": "Producto entregado a corredor - Inventario actualizado",
            "request_id": delivery.transfer_request_id,
            "inventory_updated": True,
            "delivered_at": datetime.now().isoformat(),
            "next_step": "Corredor transportará el producto"
        }
    
    async def get_inventory_by_location(self, location_id: int) -> InventoryByLocationResponse:
        """BG006: Consultar inventario disponible por ubicación"""
        inventory = self.repository.get_inventory_by_location(location_id)
        
        # Calcular resumen
        total_products = len(inventory)
        total_quantity = sum(item['quantity'] for item in inventory)
        total_value = sum(item['total_value'] for item in inventory)
        available_products = len([item for item in inventory if item['quantity'] > 0])
        
        return InventoryByLocationResponse(
            success=True,
            message=f"Inventario de Local #{location_id}",
            location_info={
                "location_id": location_id,
                "location_name": f"Local #{location_id}"
            },
            inventory=inventory,
            summary={
                "total_products": total_products,
                "available_products": available_products,
                "out_of_stock": total_products - available_products,
                "total_quantity": total_quantity,
                "total_value": total_value,
                "average_price": total_value / total_quantity if total_quantity > 0 else 0
            }
        )