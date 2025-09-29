# app/modules/transfers_new/service.py
from typing import Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .repository import TransfersRepository
from .schemas import TransferRequestCreate, TransferRequestResponse, MyTransferRequestsResponse, ReceptionConfirmation
from app.shared.services.inventory_service import InventoryService

class TransfersService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = TransfersRepository(db)
        self.inventory_service = InventoryService()
    
    async def create_transfer_request(
        self,
        transfer_data: TransferRequestCreate,
        requester_id: int
    ) -> TransferRequestResponse:
        """Crear solicitud de transferencia - igual que backend antiguo"""
        
        try:
            # Validar disponibilidad del producto
            availability = self.inventory_service.check_product_availability(
                self.db, 
                transfer_data.sneaker_reference_code, 
                transfer_data.size,
                f"Local #{transfer_data.source_location_id}"
            )
            
            if not availability['available'] or availability['quantity'] < transfer_data.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente en ubicación origen. Disponible: {availability.get('quantity', 0)}"
                )
            
            # Crear transferencia
            transfer_dict = transfer_data.dict()
            transfer = self.repository.create_transfer_request(transfer_dict, requester_id)
            
            # Determinar tiempo estimado y prioridad
            estimated_time = "30 minutos" if transfer_data.purpose == "cliente" else "45 minutos"
            priority = "high" if transfer_data.purpose == "cliente" else "normal"
            
            # Calcular expiración de reserva (si aplica)
            reservation_expires_at = None
            if transfer_data.purpose == "cliente":
                reservation_expires_at = (datetime.now() + timedelta(minutes=45)).isoformat()
            
            return TransferRequestResponse(
                success=True,
                message="Solicitud de transferencia creada exitosamente",
                transfer_request_id=transfer.id,
                status=transfer.status,
                estimated_time=estimated_time,
                priority=priority,
                next_steps=[
                    "El bodeguero revisará tu solicitud",
                    "Se confirmará disponibilidad del producto",
                    "Se asignará corredor para el transporte",
                    "Recibirás el producto en tu ubicación"
                ],
                reservation_expires_at=reservation_expires_at
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creando transferencia: {str(e)}")
    
    async def get_my_transfer_requests(self, user_id: int, user_info: Dict[str, Any]) -> MyTransferRequestsResponse:
        """Obtener mis solicitudes de transferencia - igual que backend antiguo"""
        transfers = self.repository.get_transfer_requests_by_user(user_id)
        summary = self.repository.get_transfer_summary(user_id)
        
        return MyTransferRequestsResponse(
            success=True,
            message="Vista unificada: transferencias y devoluciones en un solo lugar con mismo flujo",
            my_requests=transfers,
            summary=summary,
            vendor_info={
                "name": f"{user_info['first_name']} {user_info['last_name']}",
                "total_requests": len(transfers)
            },
            workflow_info={
                "flow": "pending → accepted → in_transit → delivered → completed",
                "difference": "Devoluciones = mismo flujo pero dirección inversa"
            }
        )
    
    async def confirm_reception(
        self,
        transfer_id: int,
        received_quantity: int,
        condition_ok: bool,
        notes: str,
        current_user: Any
    ) -> Dict[str, Any]:
        """VE008: Confirmar recepción con actualización automática de inventario"""
        
        success = self.repository.confirm_reception(
            transfer_id, received_quantity, condition_ok, notes, current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Transferencia no encontrada")
        
        return {
            "success": True,
            "message": "Recepción confirmada - Inventario actualizado automáticamente",
            "request_id": transfer_id,
            "received_quantity": received_quantity,
            "inventory_updated": condition_ok,
            "confirmed_at": datetime.now().isoformat()
        }