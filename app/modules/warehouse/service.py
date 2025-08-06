# app/modules/warehouse/service.py
import json
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal

from .repository import WarehouseRepository
from .schemas import *
from app.shared.database.models import User, Location

class WarehouseService:
    """
    Servicio principal para todas las operaciones del bodeguero
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = WarehouseRepository(db)
    
    # ==================== BG004: DEVOLUCIONES ====================
    
    async def process_return(
        self, 
        return_data: ReturnCreate, 
        warehouse_keeper: User
    ) -> ReturnResponse:
        """
        BG004: Recibir devoluciones de productos
        """
        
        # Validar que la ubicación origen existe
        origin_location = self.db.query(Location)\
            .filter(Location.id == return_data.origin_location_id).first()
        
        if not origin_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación origen no encontrada"
            )
        
        # Crear registro de devolución
        return_record_data = {
            "sneaker_reference_code": return_data.sneaker_reference_code,
            "size": return_data.size,
            "quantity": return_data.quantity,
            "reason": return_data.reason,
            "condition": return_data.condition,
            "origin_location_id": return_data.origin_location_id,
            "received_by_user_id": warehouse_keeper.id,
            "received_at": datetime.now(),
            "notes": return_data.notes,
            "status": "processed"
        }
        
        db_return = self.repository.create_return(return_record_data)
        
        # Si el producto está en buena condición, agregarlo al inventario
        if return_data.condition in ["nuevo", "good"]:
            await self._add_to_inventory(
                reference_code=return_data.sneaker_reference_code,
                size=return_data.size,
                quantity=return_data.quantity,
                location_id=warehouse_keeper.location_id,
                user_id=warehouse_keeper.id,
                reason=f"Devolución procesada - {return_data.reason}"
            )
        
        return ReturnResponse(
            id=db_return.id,
            sneaker_reference_code=db_return.sneaker_reference_code,
            size=db_return.size,
            quantity=db_return.quantity,
            reason=db_return.reason,
            condition=db_return.condition,
            origin_location_id=db_return.origin_location_id,
            origin_location_name=origin_location.name,
            received_by_user_id=db_return.received_by_user_id,
            received_by_name=warehouse_keeper.full_name,
            received_at=db_return.received_at,
            notes=db_return.notes,
            status=db_return.status
        )
    
    # ==================== BG005: UBICACIONES DE PRODUCTOS ====================
    
    async def update_product_location(
        self, 
        location_update: LocationUpdate, 
        warehouse_keeper: User
    ) -> LocationUpdateResponse:
        """
        BG005: Actualizar ubicaciones de productos entre bodegas/locales
        
        Casos de uso:
        - Traslados para exhibición
        - Redistribución entre bodegas  
        - Productos devueltos
        """
        
        # Validar ubicaciones
        source_location = self.db.query(Location)\
            .filter(Location.id == location_update.source_location_id).first()
        dest_location = self.db.query(Location)\
            .filter(Location.id == location_update.destination_location_id).first()
        
        if not source_location or not dest_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Una o ambas ubicaciones no existen"
            )
        
        # Actualizar ubicación usando el repositorio
        result = self.repository.update_product_location(
            reference_code=location_update.sneaker_reference_code,
            size=location_update.size,
            quantity=location_update.quantity,
            source_location_id=location_update.source_location_id,
            destination_location_id=location_update.destination_location_id,
            user_id=warehouse_keeper.id,
            movement_type=location_update.movement_type.value,
            reason=location_update.reason,
            notes=location_update.notes
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return LocationUpdateResponse(
            id=result["movement_id"],
            sneaker_reference_code=location_update.sneaker_reference_code,
            size=location_update.size,
            quantity=location_update.quantity,
            source_location_id=location_update.source_location_id,
            source_location_name=source_location.name,
            destination_location_id=location_update.destination_location_id,
            destination_location_name=dest_location.name,
            movement_type=location_update.movement_type.value,
            reason=location_update.reason,
            moved_by_user_id=warehouse_keeper.id,
            moved_by_name=warehouse_keeper.full_name,
            moved_at=datetime.now(),
            notes=location_update.notes
        )
    
    # ==================== BG006: INVENTARIO POR UBICACIÓN ====================
    
    async def get_inventory_by_location(
        self, 
        filters: InventoryFilter,
        warehouse_keeper: User
    ) -> List[InventoryByLocation]:
        """
        BG006: Consultar inventario disponible por ubicación general
        
        Permite al bodeguero ver qué productos hay en cada bodega o local específico
        """
        
        # Si no se especifican ubicaciones, usar las asignadas al bodeguero
        if not filters.location_ids:
            assigned_warehouses = self.repository.get_assigned_warehouses(warehouse_keeper.id)
            filters.location_ids = [w.id for w in assigned_warehouses]
        
        inventory_data = self.repository.get_inventory_by_locations(
            location_ids=filters.location_ids,
            location_type=filters.location_type,
            reference_code=filters.reference_code,
            brand=filters.brand,
            min_stock=filters.min_stock,
            max_stock=filters.max_stock
        )
        
        return [
            InventoryByLocation(
                location_id=inv["location_id"],
                location_name=inv["location_name"],
                location_type=inv["location_type"],
                total_products=inv["total_products"],
                total_units=inv["total_units"],
                products=inv["products"]
            ) for inv in inventory_data
        ]
    
    # ==================== BG007: HISTORIAL DE MOVIMIENTOS ====================
    
    async def get_movement_history(
        self,
        warehouse_keeper: User,
        filters: MovementHistoryFilter
    ) -> List[MovementHistory]:
        """
        BG007: Registrar historial de entregas y recepciones
        
        Mantiene trazabilidad completa de todos los movimientos del bodeguero
        """
        
        movements = self.repository.get_movement_history(
            user_id=warehouse_keeper.id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            movement_types=[mt.value for mt in filters.movement_types] if filters.movement_types else None,
            location_ids=filters.location_ids,
            reference_code=filters.reference_code
        )
        
        return [
            MovementHistory(
                id=mov["id"],
                movement_type=mov["movement_type"],
                sneaker_reference_code=mov["sneaker_reference_code"],
                brand=mov["brand"],
                model=mov["model"],
                size=mov["size"],
                quantity=mov["quantity_change"],
                source_location_id=mov.get("source_location_id"),
                source_location_name=mov.get("source_location_name"),
                destination_location_id=mov.get("destination_location_id"),
                destination_location_name=mov.get("destination_location_name"),
                handled_by_user_id=warehouse_keeper.id,
                handled_by_name=mov["handled_by_name"],
                handled_at=mov["handled_at"],
                notes=mov["notes"],
                related_transfer_id=mov.get("related_transfer_id")
            ) for mov in movements
        ]
    
    # ==================== BG008: MÚLTIPLES BODEGAS ====================
    
    async def get_warehouse_dashboard(self, warehouse_keeper: User) -> WarehouseDashboard:
        """
        BG008: Gestionar múltiples bodegas asignadas
        
        Dashboard completo con todas las bodegas asignadas al bodeguero
        """
        
        dashboard_data = self.repository.get_warehouse_dashboard_data(warehouse_keeper.id)
        
        assigned_warehouses = [
            AssignedWarehouse(
                location_id=w["location_id"],
                location_name=w["location_name"],
                location_type=w["location_type"],
                address=w["address"],
                phone=w["phone"],
                is_active=w["is_active"],
                total_products=0,  # Se calcularía con una query adicional
                total_units=0,     # Se calcularía con una query adicional
                pending_requests=0, # Se calcularía con una query adicional
                last_activity=None  # Se calcularía con una query adicional
            ) for w in dashboard_data["assigned_warehouses"]
        ]
        
        recent_activities = [
            MovementHistory(
                id=act["id"],
                movement_type=act["movement_type"],
                sneaker_reference_code=act["sneaker_reference_code"],
                brand=act["brand"],
                model=act["model"],
                size=act["size"],
                quantity=act["quantity_change"],
                source_location_id=act.get("location_id"),
                source_location_name=act.get("location_name"),
                destination_location_id=None,
                destination_location_name=None,
                handled_by_user_id=warehouse_keeper.id,
                handled_by_name=act["handled_by_name"],
                handled_at=act["handled_at"],
                notes=act["notes"],
                related_transfer_id=None
            ) for act in dashboard_data["recent_activities"]
        ]
        
        return WarehouseDashboard(
            user_name=warehouse_keeper.full_name,
            assigned_warehouses=assigned_warehouses,
            daily_stats=dashboard_data["daily_stats"],
            pending_tasks=dashboard_data["pending_tasks"],
            recent_activities=recent_activities
        )
    
    # ==================== BG009: DISCREPANCIAS ====================
    
    async def report_inventory_discrepancy(
        self,
        discrepancy: DiscrepancyReport,
        warehouse_keeper: User
    ) -> DiscrepancyResponse:
        """
        BG009: Reportar discrepancias de inventario
        
        Permite reportar diferencias entre el inventario físico y el sistema
        """
        
        # Validar ubicación
        location = self.db.query(Location)\
            .filter(Location.id == discrepancy.location_id).first()
        
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación no encontrada"
            )
        
        # Calcular diferencia
        difference = discrepancy.actual_quantity - discrepancy.expected_quantity
        
        discrepancy_data = {
            "location_id": discrepancy.location_id,
            "sneaker_reference_code": discrepancy.sneaker_reference_code,
            "size": discrepancy.size,
            "discrepancy_type": discrepancy.discrepancy_type.value,
            "expected_quantity": discrepancy.expected_quantity,
            "actual_quantity": discrepancy.actual_quantity,
            "difference": difference,
            "description": discrepancy.description,
            "photos": discrepancy.photos,
            "priority": discrepancy.priority,
            "reported_by_user_id": warehouse_keeper.id
        }
        
        result = self.repository.create_discrepancy_report(discrepancy_data)
        
        # Buscar información del producto para la respuesta
        from app.shared.database.models import Product
        product = self.db.query(Product)\
            .filter(Product.reference_code == discrepancy.sneaker_reference_code)\
            .first()
        
        return DiscrepancyResponse(
            id=result["id"],
            location_id=discrepancy.location_id,
            location_name=location.name,
            sneaker_reference_code=discrepancy.sneaker_reference_code,
            brand=product.brand if product else "Unknown",
            model=product.model if product else "Unknown",
            size=discrepancy.size,
            discrepancy_type=discrepancy.discrepancy_type.value,
            expected_quantity=discrepancy.expected_quantity,
            actual_quantity=discrepancy.actual_quantity,
            difference=difference,
            description=discrepancy.description,
            photos=discrepancy.photos,
            priority=discrepancy.priority,
            reported_by_user_id=warehouse_keeper.id,
            reported_by_name=warehouse_keeper.full_name,
            reported_at=result["reported_at"],
            status=result["status"],
            resolved_at=None,
            resolution_notes=None
        )
    
    # ==================== BG010: REVERSIÓN DE MOVIMIENTOS ====================
    
    async def reverse_inventory_movement(
        self,
        reversal: MovementReversal,
        warehouse_keeper: User
    ) -> MovementReversalResponse:
        """
        BG010: Revertir movimientos de inventario en caso de entrega fallida
        
        Restaura stock si corredor no puede completar entrega
        """
        
        # Buscar movimiento original
        from app.shared.database.models import InventoryChange
        original_movement = self.db.query(InventoryChange)\
            .filter(InventoryChange.id == reversal.original_movement_id).first()
        
        if not original_movement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento original no encontrado"
            )
        
        # Crear movimiento de reversión
        reversal_movement = InventoryChange(
            product_id=original_movement.product_id,
            change_type="reversal",
            size=original_movement.size,
            quantity_before=original_movement.quantity_after,
            quantity_after=original_movement.quantity_before,
            user_id=warehouse_keeper.id,
            reference_id=original_movement.id,
            notes=f"REVERSIÓN: {reversal.reason} | Movimiento original ID: {reversal.original_movement_id}. {reversal.notes or ''}"
        )
        
        self.db.add(reversal_movement)
        
        # Restaurar stock en el producto
        from app.shared.database.models import Product, ProductSize
        product = self.db.query(Product)\
            .filter(Product.id == original_movement.product_id).first()
        
        product_size = self.db.query(ProductSize)\
            .filter(
                ProductSize.product_id == product.id,
                ProductSize.size == original_movement.size
            ).first()
        
        if product_size:
            # Restaurar la cantidad original
            quantity_to_restore = original_movement.quantity_before - original_movement.quantity_after
            product_size.quantity += quantity_to_restore
        
        self.db.commit()
        self.db.refresh(reversal_movement)
        
        return MovementReversalResponse(
            id=reversal_movement.id,
            original_movement_id=reversal.original_movement_id,
            reversal_type="inventory_restoration",
            sneaker_reference_code=product.reference_code,
            size=original_movement.size,
            quantity=abs(original_movement.quantity_after - original_movement.quantity_before),
            location_affected_id=product.location_id,
            location_affected_name=product.location_name,
            reason=reversal.reason,
            reversed_by_user_id=warehouse_keeper.id,
            reversed_by_name=warehouse_keeper.full_name,
            reversed_at=reversal_movement.created_at,
            notes=reversal.notes
        )
    
    # ==================== BG010: VIDEO PARA IA ====================
    
    async def process_video_product_entry(
        self,
        video_entry: VideoProductEntry,
        video_file: UploadFile,
        warehouse_keeper: User
    ) -> VideoProcessingResponse:
        """
        BG010: Ingreso de nueva mercancía mediante video para entrenamiento de IA
        
        Procesa video mostrando el producto para entrenar IA
        """
        
        # Validar bodega
        warehouse = self.db.query(Location)\
            .filter(Location.id == video_entry.warehouse_location_id).first()
        
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bodega no encontrada"
            )
        
        # Guardar archivo de video (simulado)
        video_path = f"videos/products/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{video_file.filename}"
        
        # Simular procesamiento con IA
        ai_results = await self._process_video_with_ai(video_file)
        
        # Crear registro de procesamiento
        from app.shared.database.models import InventoryChange
        video_record = InventoryChange(
            product_id=None,  # Se relacionará después del procesamiento
            change_type="video_product_entry",
            quantity_before=0,
            quantity_after=video_entry.estimated_quantity,
            user_id=warehouse_keeper.id,
            notes=f"VIDEO ENTRY: {video_path} | Bodega: {warehouse.name} | Estimado: {video_entry.estimated_quantity} unidades. {video_entry.notes or ''}"
        )
        
        self.db.add(video_record)
        self.db.commit()
        self.db.refresh(video_record)
        
        return VideoProcessingResponse(
            id=video_record.id,
            video_file_path=video_path,
            warehouse_location_id=video_entry.warehouse_location_id,
            warehouse_name=warehouse.name,
            estimated_quantity=video_entry.estimated_quantity,
            processing_status="completed",  # En producción sería "processing"
            ai_results=ai_results,
            processed_by_user_id=warehouse_keeper.id,
            processed_by_name=warehouse_keeper.full_name,
            processed_at=video_record.created_at,
            notes=video_entry.notes
        )
    
    # ==================== MÉTODOS AUXILIARES ====================
    
    async def _add_to_inventory(
        self,
        reference_code: str,
        size: str,
        quantity: int,
        location_id: int,
        user_id: int,
        reason: str
    ):
        """Agregar producto al inventario"""
        
        from app.shared.database.models import Product, ProductSize, InventoryChange
        
        # Buscar producto existente
        product = self.db.query(Product)\
            .filter(
                Product.reference_code == reference_code,
                Product.location_id == location_id
            ).first()
        
        if not product:
            # Crear nuevo producto (requeriría más datos en producción)
            location = self.db.query(Location).filter(Location.id == location_id).first()
            product = Product(
                reference_code=reference_code,
                brand="Unknown",  # Se obtendría del escaneo o entrada manual
                model="Unknown",
                color="Unknown",
                price=0.0,
                location_id=location_id,
                location_name=location.name,
                is_active=1
            )
            self.db.add(product)
            self.db.flush()
        
        # Actualizar/crear talla
        product_size = self.db.query(ProductSize)\
            .filter(
                ProductSize.product_id == product.id,
                ProductSize.size == size
            ).first()
        
        if product_size:
            old_quantity = product_size.quantity
            product_size.quantity += quantity
            new_quantity = product_size.quantity
        else:
            old_quantity = 0
            product_size = ProductSize(
                product_id=product.id,
                size=size,
                quantity=quantity,
                quantity_exhibition=0
            )
            self.db.add(product_size)
            new_quantity = quantity
        
        # Registrar cambio
        inventory_change = InventoryChange(
            product_id=product.id,
            change_type="return_addition",
            size=size,
            quantity_before=old_quantity,
            quantity_after=new_quantity,
            user_id=user_id,
            notes=reason
        )
        self.db.add(inventory_change)
        self.db.commit()
    
    async def _process_video_with_ai(self, video_file: UploadFile) -> Dict[str, Any]:
        """Simular procesamiento de video con IA"""
        
        # En producción, aquí se enviaría el video a un servicio de IA
        await asyncio.sleep(1)  # Simular procesamiento
        
        return {
            "detected_products": [
                {
                    "reference_code": "AIR-MAX-90-001",
                    "brand": "Nike",
                    "model": "Air Max 90",
                    "color": "White/Black",
                    "confidence": 0.95,
                    "detected_sizes": ["8", "8.5", "9", "9.5", "10"],
                    "estimated_price": 120.00
                }
            ],
            "processing_time": 1.2,
            "ai_version": "v2.1.0",
            "quality_score": 0.89
        }