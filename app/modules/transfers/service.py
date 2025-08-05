from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.modules.transfers.repository import TransferRepository
from app.modules.transfers.schemas import (
    TransferRequestCreate, TransferAcceptance, CourierAcceptance,
    PickupConfirmation, DeliveryConfirmation, ReceptionConfirmation,
    TransferRequestResponse, TransferStatusInfo, TransferSummary,
    TransferDashboard, TransportIncidentCreate, TransferStatus, Purpose,
    LocationInfo, UserInfo, ProductInfo
)
from app.shared.database.models import TransferRequest, User, Location, Product, ProductSize
from app.core.auth.schemas import UserResponse


class TransferService:
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = TransferRepository(db)
    
    # ===== VENDEDOR FUNCTIONS =====
    
    def create_transfer_request(self, request_data: TransferRequestCreate, 
                              requester: UserResponse) -> TransferRequestResponse:
        """VE003: Crear solicitud de transferencia"""
        
        # Validar que la ubicación origen existe y es diferente a la del vendedor
        if request_data.source_location_id == requester.location_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes solicitar productos de tu propia ubicación"
            )
        
        # Verificar disponibilidad del producto
        availability = self.repository.check_product_availability(
            request_data.sneaker_reference_code,
            request_data.size,
            request_data.source_location_id
        )
        
        if not availability["available"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Producto no disponible. Stock actual: {availability.get('physical_stock', 0)}"
            )
        
        if availability["available_stock"] < request_data.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente. Disponible: {availability['available_stock']}, Solicitado: {request_data.quantity}"
            )
        
        # Crear solicitud
        transfer_data = {
            "source_location_id": request_data.source_location_id,
            "destination_location_id": requester.location_id,
            "sneaker_reference_code": request_data.sneaker_reference_code,
            "brand": request_data.brand,
            "model": request_data.model,
            "size": request_data.size,
            "quantity": request_data.quantity,
            "purpose": request_data.purpose.value,
            "pickup_type": request_data.pickup_type.value,
            "destination_type": request_data.destination_type.value,
            "notes": request_data.notes
        }
        
        transfer = self.repository.create_transfer_request(transfer_data, requester.id)
        
        return self._build_transfer_response(transfer, requester)
    
    def get_my_transfer_requests(self, requester: UserResponse, 
                               status_filter: Optional[List[str]] = None) -> List[TransferRequestResponse]:
        """Obtener mis solicitudes de transferencia"""
        transfers = self.repository.get_transfers_by_requester(requester.id, status_filter)
        return [self._build_transfer_response(t, requester) for t in transfers]
    
    def get_pending_receptions(self, requester: UserResponse) -> List[TransferRequestResponse]:
        """VE008: Obtener entregas pendientes de confirmación"""
        transfers = self.repository.get_pending_receptions_by_requester(requester.id)
        return [self._build_transfer_response(t, requester) for t in transfers]
    
    def confirm_reception(self, transfer_id: int, confirmation: ReceptionConfirmation, 
                         requester: UserResponse) -> Dict[str, Any]:
        """VE008: Confirmar recepción de productos"""
        
        # Verificar que la transferencia existe y pertenece al vendedor
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transferencia no encontrada"
            )
        
        if transfer.requester_id != requester.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para confirmar esta transferencia"
            )
        
        if transfer.status != "delivered":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La transferencia debe estar en estado 'delivered'. Estado actual: {transfer.status}"
            )
        
        # Actualizar inventario si todo está bien
        if confirmation.condition_ok and confirmation.received_quantity > 0:
            success = self._update_inventory_on_reception(
                transfer, confirmation.received_quantity, requester.location_id
            )
            
            if success:
                # Marcar como completada
                self.repository.update_transfer_status(
                    transfer_id, 
                    "completed",
                    received_quantity=confirmation.received_quantity,
                    reception_notes=confirmation.notes
                )
                
                return {
                    "success": True,
                    "message": "Recepción confirmada - Inventario actualizado automáticamente",
                    "inventory_updated": True,
                    "received_quantity": confirmation.received_quantity
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error actualizando inventario"
                )
        else:
            # Producto con problemas
            self.repository.update_transfer_status(
                transfer_id,
                "reception_issues",
                received_quantity=confirmation.received_quantity,
                reception_notes=f"Problemas en recepción: {confirmation.notes}"
            )
            
            return {
                "success": True,
                "message": "Recepción registrada con observaciones",
                "inventory_updated": False,
                "issues_reported": True
            }
    
    def cancel_transfer_request(self, transfer_id: int, requester: UserResponse, 
                              reason: str = "Cancelada por vendedor") -> Dict[str, Any]:
        """Cancelar solicitud de transferencia"""
        
        if not self.repository.can_cancel_transfer(transfer_id, requester.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede cancelar: transferencia no encontrada, no es tuya, o ya está en proceso"
            )
        
        success = self.repository.update_transfer_status(
            transfer_id, 
            "cancelled",
            notes=f"Cancelada: {reason}",
            cancelled_at=datetime.utcnow()
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error cancelando transferencia"
            )
        
        return {
            "success": True,
            "message": "Transferencia cancelada exitosamente",
            "cancelled_at": datetime.utcnow().isoformat(),
            "reason": reason
        }
    
    # ===== BODEGUERO FUNCTIONS =====
    
    def get_pending_requests_for_warehouse(self, warehouse_keeper: UserResponse) -> List[TransferRequestResponse]:
        """BG001: Obtener solicitudes pendientes para bodeguero"""
        transfers = self.repository.get_pending_requests_for_warehouse(warehouse_keeper.id)
        return [self._build_transfer_response(t, warehouse_keeper) for t in transfers]
    
    def get_accepted_requests_by_warehouse(self, warehouse_keeper: UserResponse) -> List[TransferRequestResponse]:
        """BG002: Obtener solicitudes aceptadas por bodeguero"""
        transfers = self.repository.get_accepted_requests_by_warehouse_keeper(warehouse_keeper.id)
        return [self._build_transfer_response(t, warehouse_keeper) for t in transfers]
    
    def accept_transfer_request(self, acceptance: TransferAcceptance, 
                              warehouse_keeper: UserResponse) -> TransferRequestResponse:
        """BG002: Aceptar/rechazar solicitud de transferencia"""
        
        transfer = self.repository.get_transfer_by_id(acceptance.transfer_request_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud no encontrada"
            )
        
        if transfer.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Solicitud no puede ser procesada. Estado actual: {transfer.status}"
            )
        
        # Verificar que el bodeguero puede gestionar esta ubicación
        # (esto se implementaría con UserLocationAssignment)
        
        if acceptance.accepted:
            # Verificar stock nuevamente
            availability = self.repository.check_product_availability(
                transfer.sneaker_reference_code,
                transfer.size,
                transfer.source_location_id
            )
            
            if not availability["available"] or availability["available_stock"] < transfer.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente. Disponible: {availability.get('available_stock', 0)}"
                )
            
            # Aceptar solicitud
            self.repository.update_transfer_status(
                acceptance.transfer_request_id,
                "accepted",
                warehouse_keeper_id=warehouse_keeper.id,
                estimated_preparation_time=acceptance.estimated_preparation_time,
                notes=acceptance.notes
            )
        else:
            # Rechazar solicitud
            self.repository.update_transfer_status(
                acceptance.transfer_request_id,
                "cancelled",
                warehouse_keeper_id=warehouse_keeper.id,
                notes=f"Rechazada por bodeguero: {acceptance.notes}"
            )
        
        # Obtener transferencia actualizada
        updated_transfer = self.repository.get_transfer_by_id(acceptance.transfer_request_id)
        return self._build_transfer_response(updated_transfer, warehouse_keeper)
    
    def deliver_to_courier(self, transfer_id: int, delivery: DeliveryConfirmation,
                          warehouse_keeper: UserResponse) -> Dict[str, Any]:
        """BG003: Entregar productos a corredor (con descuento automático)"""
        
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transferencia no encontrada"
            )
        
        if transfer.warehouse_keeper_id != warehouse_keeper.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para esta transferencia"
            )
        
        if transfer.status != "courier_assigned":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Estado incorrecto para entrega. Estado actual: {transfer.status}"
            )
        
        if delivery.delivery_successful:
            # Descontar inventario automáticamente
            success = self._update_inventory_on_pickup(
                transfer, warehouse_keeper.location_id
            )
            
            if success:
                self.repository.update_transfer_status(
                    transfer_id,
                    "in_transit",
                    pickup_notes=delivery.notes
                )
                
                return {
                    "success": True,
                    "message": "Producto entregado a corredor exitosamente",
                    "status": "in_transit",
                    "inventory_updated": True
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error actualizando inventario"
                )
        else:
            # Marcar como problema de entrega
            self.repository.update_transfer_status(
                transfer_id,
                "delivery_failed",
                pickup_notes=f"Entrega fallida: {delivery.notes}"
            )
            
            return {
                "success": True,
                "message": "Entrega marcada como fallida",
                "status": "delivery_failed",
                "inventory_updated": False
            }
    
    # ===== CORREDOR FUNCTIONS =====
    
    def get_available_requests_for_courier(self, courier: UserResponse) -> List[TransferRequestResponse]:
        """CO001: Obtener solicitudes disponibles para corredor"""
        transfers = self.repository.get_available_requests_for_courier(courier.id)
        return [self._build_transfer_response(t, courier) for t in transfers]
    
    def accept_courier_request(self, transfer_id: int, acceptance: CourierAcceptance,
                             courier: UserResponse) -> TransferRequestResponse:
        """CO002: Aceptar solicitud de transporte"""
        
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud no encontrada"
            )
        
        if transfer.status != "accepted" or transfer.courier_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Solicitud no disponible - ya fue tomada por otro corredor"
            )
        
        # Asignar corredor
        success = self.repository.update_transfer_status(
            transfer_id,
            "courier_assigned",
            courier_id=courier.id,
            estimated_pickup_time=acceptance.estimated_pickup_time,
            courier_notes=acceptance.notes
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error asignando solicitud"
            )
        
        updated_transfer = self.repository.get_transfer_by_id(transfer_id)
        return self._build_transfer_response(updated_transfer, courier)
    
    def confirm_pickup(self, transfer_id: int, confirmation: PickupConfirmation,
                      courier: UserResponse) -> Dict[str, Any]:
        """CO003: Confirmar recolección"""
        
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transferencia no encontrada"
            )
        
        if transfer.courier_id != courier.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para esta transferencia"
            )
        
        if transfer.status != "courier_assigned":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Estado incorrecto. Estado actual: {transfer.status}"
            )
        
        success = self.repository.update_transfer_status(
            transfer_id,
            "in_transit",
            pickup_notes=confirmation.pickup_notes
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error confirmando recolección"
            )
        
        return {
            "success": True,
            "message": "Recolección confirmada - Producto en tránsito",
            "status": "in_transit",
            "next_step": "Dirigirse al punto de entrega"
        }
    
    def confirm_delivery(self, transfer_id: int, confirmation: DeliveryConfirmation,
                        courier: UserResponse) -> Dict[str, Any]:
        """CO004: Confirmar entrega"""
        
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transferencia no encontrada"
            )
        
        if transfer.courier_id != courier.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para esta transferencia"
            )
        
        if transfer.status != "in_transit":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Estado incorrecto. Estado actual: {transfer.status}"
            )
        
        if confirmation.delivery_successful:
            success = self.repository.update_transfer_status(
                transfer_id,
                "delivered",
                courier_notes=confirmation.notes
            )
            
            return {
                "success": True,
                "message": "Entrega confirmada exitosamente",
                "status": "delivered",
                "next_step": "Vendedor debe confirmar recepción"
            }
        else:
            success = self.repository.update_transfer_status(
                transfer_id,
                "delivery_failed",
                courier_notes=f"Entrega fallida: {confirmation.notes}"
            )
            
            return {
                "success": True,
                "message": "Entrega marcada como fallida",
                "status": "delivery_failed",
                "notes": confirmation.notes
            }
    
    def report_incident(self, transfer_id: int, incident: TransportIncidentCreate,
                       courier: UserResponse) -> Dict[str, Any]:
        """CO005: Reportar incidencia de transporte"""
        
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transferencia no encontrada"
            )
        
        if transfer.courier_id != courier.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para reportar incidencias en esta transferencia"
            )
        
        incident_id = self.repository.create_transport_incident(
            transfer_id,
            courier.id,
            {
                "incident_type": incident.incident_type,
                "description": incident.description
            }
        )
        
        if not incident_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creando incidencia"
            )
        
        return {
            "success": True,
            "message": "Incidencia reportada exitosamente",
            "incident_id": incident_id,
            "transfer_id": transfer_id
        }
    
    def get_courier_delivery_history(self, courier: UserResponse) -> List[TransferRequestResponse]:
        """CO006: Historial de entregas del corredor"""
        transfers = self.repository.get_courier_delivery_history(courier.id)
        return [self._build_transfer_response(t, courier) for t in transfers]
    
    # ===== DASHBOARD Y MÉTRICAS =====
    
    def get_transfer_dashboard(self, user: UserResponse) -> TransferDashboard:
        """Dashboard de transferencias según rol"""
        
        if user.role == "vendedor":
            transfers = self.get_my_transfer_requests(user, ["pending", "accepted", "in_transit", "delivered"])
        elif user.role == "bodeguero":
            pending = self.get_pending_requests_for_warehouse(user)
            accepted = self.get_accepted_requests_by_warehouse(user)
            transfers = pending + accepted
        elif user.role == "corredor":
            transfers = self.get_available_requests_for_courier(user)
        else:
            transfers = []
        
        # Calcular resumen
        summary = self._calculate_transfer_summary(transfers)
        
        # Detectar items que requieren atención
        attention_needed = self._detect_attention_needed(transfers, user.role)
        
        return TransferDashboard(
            transfers=transfers,
            summary=summary,
            attention_needed=attention_needed,
            user_info={
                "name": f"{user.first_name} {user.last_name}",
                "role": user.role,
                "location_id": user.location_id
            },
            last_updated=datetime.utcnow()
        )
    
    # ===== HELPER METHODS =====
    
    def _build_transfer_response(self, transfer: TransferRequest, 
                               user: UserResponse) -> TransferRequestResponse:
        """Construir respuesta de transferencia con permisos"""
        
        # Información del producto
        product_info = ProductInfo(
            reference_code=transfer.sneaker_reference_code,
            brand=transfer.brand,
            model=transfer.model,
            size=transfer.size,
            quantity=transfer.quantity
        )
        
        # Información de ubicaciones
        source_location = LocationInfo(
            id=transfer.source_location.id,
            name=transfer.source_location.name,
            type=transfer.source_location.type,
            address=transfer.source_location.address
        )
        
        destination_location = LocationInfo(
            id=transfer.destination_location.id,
            name=transfer.destination_location.name,
            type=transfer.destination_location.type,
            address=transfer.destination_location.address
        )
        
        # Información de participantes
        requester = UserInfo(
            id=transfer.requester.id,
            first_name=transfer.requester.first_name,
            last_name=transfer.requester.last_name
        )
        
        warehouse_keeper = None
        if transfer.warehouse_keeper:
            warehouse_keeper = UserInfo(
                id=transfer.warehouse_keeper.id,
                first_name=transfer.warehouse_keeper.first_name,
                last_name=transfer.warehouse_keeper.last_name
            )
        
        courier = None
        if transfer.courier:
            courier = UserInfo(
                id=transfer.courier.id,
                first_name=transfer.courier.first_name,
                last_name=transfer.courier.last_name
            )
        
        # Calcular permisos según rol y estado
        permissions = self._calculate_permissions(transfer, user)
        
        return TransferRequestResponse(
            id=transfer.id,
            status=TransferStatus(transfer.status),
            purpose=Purpose(transfer.purpose),
            pickup_type=transfer.pickup_type,
            destination_type=transfer.destination_type,
            product_info=product_info,
            source_location=source_location,
            destination_location=destination_location,
            requester=requester,
            warehouse_keeper=warehouse_keeper,
            courier=courier,
            requested_at=transfer.requested_at,
            accepted_at=transfer.accepted_at,
            picked_up_at=transfer.picked_up_at,
            delivered_at=transfer.delivered_at,
            confirmed_reception_at=transfer.confirmed_reception_at,
            notes=transfer.notes,
            reception_notes=transfer.reception_notes,
            estimated_pickup_time=transfer.estimated_pickup_time,
            **permissions
        )
    
    def _calculate_permissions(self, transfer: TransferRequest, 
                             user: UserResponse) -> Dict[str, bool]:
        """Calcular permisos según rol y estado"""
        
        permissions = {
            "can_cancel": False,
            "can_accept": False,
            "can_pickup": False,
            "can_deliver": False,
            "can_confirm_reception": False
        }
        
        status = transfer.status
        
        if user.role == "vendedor" and transfer.requester_id == user.id:
            permissions["can_cancel"] = status in ["pending", "accepted"]
            permissions["can_confirm_reception"] = status == "delivered"
        
        elif user.role == "bodeguero":
            permissions["can_accept"] = status == "pending"
            permissions["can_pickup"] = (status == "courier_assigned" and 
                                       transfer.warehouse_keeper_id == user.id)
        
        elif user.role == "corredor":
            permissions["can_accept"] = (status == "accepted" and 
                                       transfer.courier_id is None)
            permissions["can_pickup"] = (status == "courier_assigned" and 
                                       transfer.courier_id == user.id)
            permissions["can_deliver"] = (status == "in_transit" and 
                                        transfer.courier_id == user.id)
        
        return permissions
    
    def _calculate_transfer_summary(self, transfers: List[TransferRequestResponse]) -> TransferSummary:
        """Calcular resumen de transferencias"""
        
        summary = TransferSummary(
            total_requests=len(transfers),
            pending=0,
            accepted=0,
            in_transit=0,
            delivered=0,
            completed=0,
            cancelled=0
        )
        
        for transfer in transfers:
            status = transfer.status.value
            if status == "pending":
                summary.pending += 1
            elif status == "accepted":
                summary.accepted += 1
            elif status == "in_transit":
                summary.in_transit += 1
            elif status == "delivered":
                summary.delivered += 1
            elif status == "completed":
                summary.completed += 1
            elif status == "cancelled":
                summary.cancelled += 1
        
        return summary
    
    def _detect_attention_needed(self, transfers: List[TransferRequestResponse], 
                               role: str) -> List[Dict[str, Any]]:
        """Detectar transferencias que requieren atención"""
        
        attention = []
        now = datetime.utcnow()
        
        for transfer in transfers:
            # Transferencias urgentes (cliente presente) pendientes
            if (transfer.purpose == Purpose.CLIENTE and 
                transfer.status == TransferStatus.PENDING):
                hours_waiting = (now - transfer.requested_at).total_seconds() / 3600
                if hours_waiting > 0.5:  # Más de 30 minutos
                    attention.append({
                        "transfer_id": transfer.id,
                        "type": "urgent_client_waiting",
                        "message": f"Cliente esperando hace {hours_waiting:.1f} horas",
                        "urgency": "high"
                    })
            
            # Entregas pendientes de confirmación por mucho tiempo
            if (transfer.status == TransferStatus.DELIVERED and role == "vendedor"):
                hours_delivered = (now - transfer.delivered_at).total_seconds() / 3600
                if hours_delivered > 2:  # Más de 2 horas
                    attention.append({
                        "transfer_id": transfer.id,
                        "type": "pending_reception",
                        "message": f"Entrega sin confirmar hace {hours_delivered:.1f} horas",
                        "urgency": "medium"
                    })
        
        return attention
    
    def _update_inventory_on_pickup(self, transfer: TransferRequest, 
                                  warehouse_location_id: int) -> bool:
        """Descontar inventario cuando bodeguero entrega a corredor"""
        try:
            # Buscar el producto en la ubicación de origen
            location = self.db.query(Location).filter(
                Location.id == warehouse_location_id
            ).first()
            
            if not location:
                return False
            
            # Buscar el ProductSize específico
            product_size = self.db.query(ProductSize).join(Product).filter(
                Product.reference_code == transfer.sneaker_reference_code,
                Product.location_name == location.name,
                ProductSize.size == transfer.size,
                Product.is_active == 1
            ).first()
            
            if not product_size or product_size.quantity < transfer.quantity:
                return False
            
            # Descontar inventario
            product_size.quantity -= transfer.quantity
            self.db.commit()
            
            return True
            
        except Exception as e:
            self.db.rollback()
            return False
    
    def _update_inventory_on_reception(self, transfer: TransferRequest, 
                                     quantity: int, vendor_location_id: int) -> bool:
        """Agregar inventario cuando vendedor confirma recepción"""
        try:
            # Buscar ubicación del vendedor
            location = self.db.query(Location).filter(
                Location.id == vendor_location_id
            ).first()
            
            if not location:
                return False
            
            # Buscar producto existente en la ubicación del vendedor
            existing_product = self.db.query(Product).filter(
                Product.reference_code == transfer.sneaker_reference_code,
                Product.location_name == location.name
            ).first()
            
            if existing_product:
                # Producto existe, buscar talla
                product_size = self.db.query(ProductSize).filter(
                    ProductSize.product_id == existing_product.id,
                    ProductSize.size == transfer.size
                ).first()
                
                if product_size:
                    # Talla existe, sumar cantidad
                    product_size.quantity += quantity
                else:
                    # Crear nueva talla
                    new_size = ProductSize(
                        product_id=existing_product.id,
                        size=transfer.size,
                        quantity=quantity,
                        quantity_exhibition=0,
                        location_name=location.name
                    )
                    self.db.add(new_size)
            else:
                # Producto no existe, crear desde información de transferencia
                # Buscar información del producto en ubicación origen
                source_product = self.db.query(Product).filter(
                    Product.reference_code == transfer.sneaker_reference_code
                ).first()
                
                if source_product:
                    # Crear producto en ubicación destino
                    new_product = Product(
                        reference_code=transfer.sneaker_reference_code,
                        description=f"{transfer.brand} {transfer.model}",
                        brand=transfer.brand,
                        model=transfer.model,
                        color_info=source_product.color_info or "Varios",
                        location_name=location.name,
                        unit_price=source_product.unit_price,
                        box_price=source_product.box_price,
                        is_active=1,
                        image_url=source_product.image_url,
                        video_url=source_product.video_url
                    )
                    self.db.add(new_product)
                    self.db.flush()  # Para obtener el ID
                    
                    # Crear talla
                    new_size = ProductSize(
                        product_id=new_product.id,
                        size=transfer.size,
                        quantity=quantity,
                        quantity_exhibition=0,
                        location_name=location.name
                    )
                    self.db.add(new_size)
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            return False