# app/modules/sales_new/service.py
import json
from typing import Dict, Any, List
from datetime import date, datetime
from decimal import Decimal
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .repository import SalesRepository
from .schemas import SaleCreateRequest, SaleResponse, DailySalesResponse
from app.shared.services.inventory_service import InventoryService

class SalesService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SalesRepository(db)
        self.inventory_service = InventoryService()
    
    async def create_sale_complete(
        self,
        sale_data: SaleCreateRequest,
        receipt_image: UploadFile,
        seller_id: int,
        location_id: int
    ) -> SaleResponse:
        """Crear venta completa con actualización de inventario"""
        
        try:
            # 1. Validar disponibilidad de productos
            await self._validate_product_availability(sale_data.items, f"Local #{location_id}")
            
            # 2. Crear venta en BD
            sale_dict = sale_data.dict()
            sale = self.repository.create_sale(sale_dict, seller_id, location_id)
            
            # 3. Actualizar inventario
            items_for_inventory = [
                {
                    'sneaker_reference_code': item.sneaker_reference_code,
                    'size': item.size,
                    'quantity': item.quantity
                }
                for item in sale_data.items
            ]
            
            inventory_updated = self.inventory_service.update_stock_after_sale(
                self.db, items_for_inventory, seller_id, f"Local #{location_id}"
            )
            
            if not inventory_updated:
                # Rollback sale if inventory update fails
                self.db.delete(sale)
                self.db.commit()
                raise HTTPException(
                    status_code=400,
                    detail="Error actualizando inventario. Venta cancelada."
                )
            
            # 4. Procesar imagen de recibo si existe
            receipt_path = None
            if receipt_image:
                receipt_path = await self._save_receipt_image(receipt_image, sale.id)
            
            return SaleResponse(
                success=True,
                message="Venta registrada exitosamente",
                sale_id=sale.id,
                total_amount=sale.total_amount,
                status=sale.status,
                requires_confirmation=sale.requires_confirmation,
                created_at=sale.sale_date,
                items_count=len(sale_data.items),
                payment_methods_count=len(sale_data.payment_methods),
                inventory_updated=inventory_updated
            )
            
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creando venta: {str(e)}")
    
    async def get_daily_sales(self, seller_id: int, target_date: date) -> DailySalesResponse:
        """Obtener ventas del día"""
        sales = self.repository.get_sales_by_seller_and_date(seller_id, target_date)
        summary = self.repository.get_daily_sales_summary(seller_id, target_date)
        
        sales_data = []
        for sale in sales:
            items = self.repository.get_sale_items(sale.id)
            sales_data.append({
                "id": sale.id,
                "total_amount": float(sale.total_amount),
                "status": sale.status,
                "confirmed": sale.confirmed,
                "requires_confirmation": sale.requires_confirmation,
                "sale_date": sale.sale_date.isoformat(),
                "items_count": len(items),
                "notes": sale.notes
            })
        
        return DailySalesResponse(
            success=True,
            message=f"Ventas del {target_date}",
            date=target_date.isoformat(),
            sales=sales_data,
            summary=summary,
            seller_info={"seller_id": seller_id}
        )
    
    async def confirm_sale(self, sale_id: int, confirmed: bool, confirmation_notes: str, user_id: int) -> Dict[str, Any]:
        """Confirmar o rechazar una venta"""
        success = self.repository.confirm_sale(sale_id, confirmed, confirmation_notes, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Venta no encontrada")
        
        return {
            "success": True,
            "message": "Venta confirmada" if confirmed else "Venta rechazada",
            "sale_id": sale_id,
            "confirmed": confirmed,
            "confirmed_at": datetime.now().isoformat()
        }
    
    async def get_pending_confirmation_sales(self, seller_id: int) -> Dict[str, Any]:
        """Obtener ventas pendientes de confirmación"""
        pending_sales = self.repository.get_pending_confirmation_sales(seller_id)
        
        sales_data = []
        total_pending = Decimal('0')
        
        for sale in pending_sales:
            sales_data.append({
                "id": sale.id,
                "total_amount": float(sale.total_amount),
                "sale_date": sale.sale_date.isoformat(),
                "notes": sale.notes,
                "items_count": len(self.repository.get_sale_items(sale.id))
            })
            total_pending += sale.total_amount
        
        return {
            "success": True,
            "pending_sales": sales_data,
            "count": len(sales_data),
            "total_pending_amount": float(total_pending)
        }
    
    async def _validate_product_availability(self, items: List, location_name: str):
        """Validar que todos los productos estén disponibles"""
        for item in items:
            availability = self.inventory_service.check_product_availability(
                self.db, item.sneaker_reference_code, item.size, location_name
            )
            
            if not availability['available'] or availability['quantity'] < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente para {item.sneaker_reference_code} talla {item.size}"
                )
    
    async def _save_receipt_image(self, image: UploadFile, sale_id: int) -> str:
        """Guardar imagen de recibo"""
        # Implementar lógica de guardado de imagen
        # Por ahora retornamos un path simulado
        return f"receipts/sale_{sale_id}_{image.filename}"