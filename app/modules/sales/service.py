# app/modules/sales/service.py
import json
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from decimal import Decimal

from app.shared.database.models import (
    Sale, SaleItem, SalePayment, Expense, Product, ProductSize,
    DiscountRequest, ProductReservation, User, Location
)
from .repository import SalesRepository
from .schemas import (
    SaleCreateRequest, ExpenseCreateRequest, 
    ProductScanResponse, DailySalesResponse, VendorDashboardResponse
)

class SalesService:
    """
    Servicio principal para todas las operaciones de ventas del vendedor
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = SalesRepository(db)
    
    # ==================== VE001: ESCANEO CON IA ====================
    
    async def scan_product_with_ai(
        self, 
        image_file: UploadFile, 
        user_location_id: int,
        include_alternatives: bool = True
    ) -> ProductScanResponse:
        """
        VE001: Escanear productos usando reconocimiento de imágenes con IA
        """
        start_time = datetime.now()
        
        try:
            # 1. Procesar imagen con IA (simulado por ahora)
            ai_result = await self._process_image_with_ai(image_file)
            
            # 2. Buscar productos en base de datos
            products_found = []
            for ai_match in ai_result.get('matches', []):
                product_info = await self._get_product_with_availability(
                    reference_code=ai_match['reference_code'],
                    user_location_id=user_location_id
                )
                if product_info:
                    products_found.append(product_info)
            
            # 3. Buscar alternativas si se solicita
            alternatives = []
            if include_alternatives and products_found:
                alternatives = await self._find_alternative_products(
                    products_found[0] if products_found else None,
                    user_location_id
                )
            
            # 4. Preparar respuesta
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return ProductScanResponse(
                success=True,
                scan_timestamp=start_time,
                scanned_by={
                    "user_location_id": user_location_id,
                    "location_name": f"Local #{user_location_id}"
                },
                best_match=products_found[0] if products_found else None,
                alternative_matches=products_found[1:3] if len(products_found) > 1 else [],
                total_matches_found=len(products_found),
                availability_summary=self._calculate_availability_summary(products_found),
                processing_time_ms=processing_time,
                image_info={
                    "filename": image_file.filename,
                    "content_type": image_file.content_type,
                    "size_bytes": 0  # Se calculará después
                },
                classification_service={
                    "service": "ai_classification",
                    "model": "sneaker-recognition-v2",
                    "confidence_threshold": 0.7
                }
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error en escaneo con IA: {str(e)}")
    
    async def _process_image_with_ai(self, image_file: UploadFile) -> Dict[str, Any]:
        """
        Procesar imagen con IA (simulado por ahora)
        En producción se conectaría al microservicio real
        """
        # Simular procesamiento de IA
        await asyncio.sleep(0.5)  # Simular tiempo de procesamiento
        
        # Retornar resultado simulado
        return {
            "success": True,
            "matches": [
                {
                    "reference_code": "NK-AF1-001",
                    "confidence": 0.95,
                    "brand": "Nike",
                    "model": "Air Force 1"
                },
                {
                    "reference_code": "AD-UB22-001", 
                    "confidence": 0.85,
                    "brand": "Adidas",
                    "model": "Ultraboost 22"
                }
            ]
        }
    
    async def _get_product_with_availability(
        self, 
        reference_code: str, 
        user_location_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Obtener producto con información de disponibilidad
        """
        product = self.repository.get_product_by_reference(reference_code)
        if not product:
            return None
        
        # Obtener stock en ubicación actual
        current_stock = self.repository.get_product_stock_by_location(
            reference_code, user_location_id
        )
        
        # Obtener stock en otras ubicaciones
        other_locations_stock = self.repository.get_product_stock_other_locations(
            reference_code, user_location_id
        )
        
        # Verificar disponibilidad considerando reservas
        availability = self._check_product_availability(
            reference_code, user_location_id
        )
        
        return {
            "reference_code": product.reference_code,
            "brand": product.brand,
            "model": product.model,
            "description": product.description,
            "color": product.color_info,
            "unit_price": float(product.unit_price),
            "box_price": float(product.box_price),
            "image_url": product.image_url,
            "current_location_stock": current_stock,
            "other_locations_stock": other_locations_stock,
            "availability": availability,
            "can_request_transfer": len(other_locations_stock) > 0,
            "estimated_transfer_time": "2-4 horas" if other_locations_stock else None
        }
    
    async def _find_alternative_products(
        self, 
        base_product: Optional[Dict[str, Any]], 
        user_location_id: int
    ) -> List[Dict[str, Any]]:
        """
        VE018: Encontrar productos similares disponibles
        """
        if not base_product:
            return []
        
        alternatives = self.repository.find_similar_products(
            brand=base_product.get('brand'),
            model=base_product.get('model'),
            exclude_reference=base_product.get('reference_code'),
            location_id=user_location_id,
            limit=3
        )
        
        return alternatives
    
    def _check_product_availability(
        self, 
        reference_code: str, 
        location_id: int
    ) -> Dict[str, Any]:
        """
        Verificar disponibilidad considerando reservas activas
        """
        # Stock físico
        physical_stock = self.repository.get_total_stock_by_location(
            reference_code, location_id
        )
        
        # Reservas activas
        reserved_quantity = self.repository.get_reserved_quantity(
            reference_code, location_id
        )
        
        available_stock = physical_stock - reserved_quantity
        
        return {
            "physical_stock": physical_stock,
            "reserved_quantity": reserved_quantity,
            "available_stock": max(0, available_stock),
            "can_fulfill": available_stock > 0
        }
    
    def _calculate_availability_summary(
        self, 
        products_found: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calcular resumen de disponibilidad para múltiples productos
        """
        available_locally = sum(1 for p in products_found 
                               if p.get('availability', {}).get('can_fulfill', False))
        transfer_available = sum(1 for p in products_found 
                                if p.get('can_request_transfer', False))
        
        return {
            "products_available_locally": available_locally,
            "products_requiring_transfer": transfer_available,
            "total_products_found": len(products_found),
            "can_sell_immediately": available_locally > 0,
            "transfer_options_available": transfer_available > 0
        }
    
    # ==================== VE002: REGISTRO DE VENTAS ====================
    
    async def create_sale_complete(
        self,
        sale_data: SaleCreateRequest,
        receipt_image: Optional[UploadFile],
        seller_id: int,
        location_id: int
    ) -> Dict[str, Any]:
        """
        VE002: Registrar venta completa con múltiples métodos de pago
        """
        try:
            # 1. Validar stock disponible
            stock_issues = self._validate_stock_availability(
                sale_data.items, location_id
            )
            if stock_issues:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente: {stock_issues}"
                )
            
            # 2. Subir imagen del comprobante si existe
            receipt_url = None
            if receipt_image:
                receipt_url = await self._upload_receipt_image(receipt_image, seller_id)
            
            # 3. Crear la venta
            sale = self.repository.create_sale(
                seller_id=seller_id,
                location_id=location_id,
                total_amount=sale_data.total_amount,
                receipt_image=receipt_url,
                notes=sale_data.notes,
                requires_confirmation=sale_data.requires_confirmation
            )
            
            # 4. Crear items de la venta
            sale_items = []
            for item in sale_data.items:
                sale_item = self.repository.create_sale_item(
                    sale_id=sale.id,
                    item_data=item
                )
                sale_items.append(sale_item)
            
            # 5. Crear métodos de pago
            payment_methods = []
            for payment in sale_data.payment_methods:
                payment_method = self.repository.create_sale_payment(
                    sale_id=sale.id,
                    payment_data=payment
                )
                payment_methods.append(payment_method)
            
            # 6. Actualizar stock si no requiere confirmación
            if not sale_data.requires_confirmation:
                self._update_stock_after_sale(sale_data.items, location_id)
            
            # 7. Preparar respuesta
            return {
                "success": True,
                "sale_id": sale.id,
                "message": "Venta registrada exitosamente",
                "sale_timestamp": sale.sale_date.isoformat(),
                "status": "pending_confirmation" if sale_data.requires_confirmation else "completed",
                "receipt_uploaded": bool(receipt_url),
                "items_count": len(sale_items),
                "total_amount": float(sale_data.total_amount)
            }
            
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error registrando venta: {str(e)}")
    
    async def confirm_sale(
        self,
        sale_id: int,
        confirmed: bool,
        confirmation_notes: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Confirmar una venta pendiente
        """
        sale = self.repository.get_sale_by_id(sale_id)
        if not sale or sale.seller_id != user_id:
            raise HTTPException(status_code=404, detail="Venta no encontrada")
        
        if not sale.requires_confirmation:
            raise HTTPException(status_code=400, detail="Esta venta no requiere confirmación")
        
        # Actualizar confirmación
        updated_sale = self.repository.confirm_sale(
            sale_id=sale_id,
            confirmed=confirmed,
            confirmation_notes=confirmation_notes
        )
        
        # Si se confirma, actualizar stock
        if confirmed:
            sale_items = self.repository.get_sale_items(sale_id)
            self._update_stock_after_sale(sale_items, sale.location_id)
        
        return {
            "success": True,
            "sale_id": sale_id,
            "confirmed": confirmed,
            "message": "Venta confirmada exitosamente" if confirmed else "Venta no confirmada",
            "confirmation_timestamp": datetime.now().isoformat()
        }
    
    def _validate_stock_availability(
        self, 
        items: List[Any], 
        location_id: int
    ) -> List[Dict[str, Any]]:
        """
        Validar que hay stock suficiente para todos los items
        """
        stock_issues = []
        
        for item in items:
            availability = self._check_product_availability(
                item.sneaker_reference_code, location_id
            )
            
            if availability['available_stock'] < item.quantity:
                stock_issues.append({
                    "reference": item.sneaker_reference_code,
                    "size": item.size,
                    "requested": item.quantity,
                    "available": availability['available_stock']
                })
        
        return stock_issues
    
    def _update_stock_after_sale(
        self, 
        items: List[Any], 
        location_id: int
    ):
        """
        Actualizar stock después de confirmar venta
        """
        for item in items:
            self.repository.decrease_product_stock(
                reference_code=item.sneaker_reference_code,
                size=item.size,
                quantity=item.quantity,
                location_id=location_id
            )
    
    async def _upload_receipt_image(
        self, 
        image_file: UploadFile, 
        user_id: int
    ) -> str:
        """
        Subir imagen del comprobante (simulado)
        En producción se conectaría a Cloudinary o servicio similar
        """
        # Simular upload
        await asyncio.sleep(0.2)
        
        # Simular URL de imagen
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"https://storage.tustockya.com/receipts/{user_id}/{timestamp}_{image_file.filename}"
    
    # ==================== VE003: CONSULTA DE PRODUCTOS ====================
    
    async def search_products_by_reference(
        self,
        reference_code: str,
        current_location_id: int,
        include_other_locations: bool = True
    ) -> List[Dict[str, Any]]:
        """
        VE003: Buscar productos por referencia en todas las ubicaciones
        """
        products = []
        
        # Buscar en ubicación actual
        current_product = await self._get_product_with_availability(
            reference_code, current_location_id
        )
        if current_product:
            products.append(current_product)
        
        # Buscar en otras ubicaciones si se solicita
        if include_other_locations:
            other_locations = self.repository.get_product_in_other_locations(
                reference_code, current_location_id
            )
            products.extend(other_locations)
        
        return products
    
    # ==================== VE004: GASTOS OPERATIVOS ====================
    
    async def create_expense(
        self,
        expense_data: ExpenseCreateRequest,
        receipt_image: Optional[UploadFile],
        user_id: int,
        location_id: int
    ) -> Dict[str, Any]:
        """
        VE004: Registrar gastos operativos
        """
        try:
            # Subir imagen del comprobante si existe
            receipt_url = None
            if receipt_image:
                receipt_url = await self._upload_receipt_image(receipt_image, user_id)
            
            # Crear gasto
            expense = self.repository.create_expense(
                user_id=user_id,
                location_id=location_id,
                concept=expense_data.concept,
                amount=expense_data.amount,
                receipt_image=receipt_url,
                notes=expense_data.notes
            )
            
            return {
                "success": True,
                "expense_id": expense.id,
                "message": "Gasto registrado exitosamente",
                "expense_timestamp": expense.expense_date.isoformat(),
                "has_receipt": bool(receipt_url),
                "amount": float(expense.amount)
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error registrando gasto: {str(e)}")
    
    async def get_expenses_by_date(
        self,
        user_id: int,
        location_id: int,
        date: date
    ) -> Dict[str, Any]:
        """
        Obtener gastos por fecha
        """
        expenses = self.repository.get_expenses_by_user_and_date(
            user_id, location_id, date
        )
        
        total_amount = sum(expense.amount for expense in expenses)
        
        return {
            "success": True,
            "date": date.isoformat(),
            "expenses": [
                {
                    "id": expense.id,
                    "concept": expense.concept,
                    "amount": float(expense.amount),
                    "receipt_image": expense.receipt_image,
                    "expense_date": expense.expense_date.isoformat(),
                    "notes": expense.notes,
                    "has_receipt": bool(expense.receipt_image)
                }
                for expense in expenses
            ],
            "summary": {
                "total_expenses": len(expenses),
                "total_amount": float(total_amount)
            }
        }
    
    # ==================== VE005: VENTAS DEL DÍA ====================
    
    async def get_daily_sales(
        self,
        seller_id: int,
        location_id: int,
        date: date
    ) -> DailySalesResponse:
        """
        VE005: Consultar ventas realizadas en el día
        """
        sales = self.repository.get_sales_by_seller_and_date(
            seller_id, location_id, date
        )
        
        # Calcular estadísticas
        total_amount = sum(sale.total_amount for sale in sales if sale.confirmed)
        confirmed_sales = [sale for sale in sales if sale.confirmed]
        pending_sales = [sale for sale in sales if sale.requires_confirmation and not sale.confirmed]
        
        # Estadísticas por método de pago
        payment_stats = self._calculate_payment_method_stats(confirmed_sales)
        
        sales_data = []
        for sale in sales:
            sale_items = self.repository.get_sale_items(sale.id)
            sale_payments = self.repository.get_sale_payments(sale.id)
            
            sales_data.append({
                "id": sale.id,
                "total_amount": float(sale.total_amount),
                "sale_date": sale.sale_date.isoformat(),
                "status": sale.status,
                "confirmed": sale.confirmed,
                "requires_confirmation": sale.requires_confirmation,
                "receipt_image": sale.receipt_image,
                "notes": sale.notes,
                "items": [
                    {
                        "id": item.id,
                        "sneaker_reference_code": item.sneaker_reference_code,
                        "brand": item.brand,
                        "model": item.model,
                        "size": item.size,
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price),
                        "subtotal": float(item.subtotal)
                    }
                    for item in sale_items
                ],
                "payments": [
                    {
                        "id": payment.id,
                        "payment_type": payment.payment_type,
                        "amount": float(payment.amount),
                        "reference": payment.reference
                    }
                    for payment in sale_payments
                ]
            })
        
        return DailySalesResponse(
            success=True,
            date=date.isoformat(),
            sales=sales_data,
            summary={
                "total_sales": len(sales),
                "confirmed_sales": len(confirmed_sales),
                "pending_confirmation": len(pending_sales),
                "total_amount": float(total_amount),
                "payment_methods_stats": payment_stats,
                "average_sale": float(total_amount / len(confirmed_sales)) if confirmed_sales else 0
            }
        )
    
    def _calculate_payment_method_stats(self, sales: List[Sale]) -> Dict[str, Dict[str, float]]:
        """
        Calcular estadísticas por método de pago
        """
        stats = {}
        
        for sale in sales:
            payments = self.repository.get_sale_payments(sale.id)
            for payment in payments:
                if payment.payment_type not in stats:
                    stats[payment.payment_type] = {"count": 0, "amount": 0}
                
                stats[payment.payment_type]["count"] += 1
                stats[payment.payment_type]["amount"] += float(payment.amount)
        
        return stats
    
    async def get_pending_confirmation_sales(
        self,
        seller_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtener ventas pendientes de confirmación
        """
        pending_sales = self.repository.get_pending_confirmation_sales(seller_id)
        
        sales_data = []
        for sale in pending_sales:
            sale_items = self.repository.get_sale_items(sale.id)
            sale_payments = self.repository.get_sale_payments(sale.id)
            
            sales_data.append({
                "id": sale.id,
                "total_amount": float(sale.total_amount),
                "sale_date": sale.sale_date.isoformat(),
                "notes": sale.notes,
                "items_count": len(sale_items),
                "payments_count": len(sale_payments)
            })
        
        return sales_data
    
    # ==================== VE007: SOLICITUDES DE DESCUENTO ====================
    
    async def create_discount_request(
        self,
        amount: float,
        reason: str,
        seller_id: int
    ) -> Dict[str, Any]:
        """
        VE007: Solicitar descuentos hasta $5,000
        """
        discount_request = self.repository.create_discount_request(
            seller_id=seller_id,
            amount=amount,
            reason=reason
        )
        
        return {
            "success": True,
            "discount_request_id": discount_request.id,
            "message": "Solicitud de descuento enviada al administrador",
            "amount": float(amount),
            "status": "pending",
            "requested_at": discount_request.requested_at.isoformat()
        }
    
    async def get_discount_requests_by_seller(
        self,
        seller_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtener solicitudes de descuento de un vendedor
        """
        requests = self.repository.get_discount_requests_by_seller(seller_id)
        
        return [
            {
                "id": request.id,
                "amount": float(request.amount),
                "reason": request.reason,
                "status": request.status,
                "requested_at": request.requested_at.isoformat(),
                "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
                "admin_comments": request.admin_comments
            }
            for request in requests
        ]
    
    # ==================== VE016: SISTEMA DE RESERVAS ====================
    
    async def reserve_product(
        self,
        reference_code: str,
        size: str,
        quantity: int,
        purpose: str,
        notes: str,
        user_id: int,
        location_id: int
    ) -> Dict[str, Any]:
        """
        VE016: Reservar producto para cliente presente o restock
        """
        # Verificar disponibilidad
        availability = self._check_product_availability(reference_code, location_id)
        if not availability['can_fulfill'] or availability['available_stock'] < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente. Disponible: {availability['available_stock']}, Solicitado: {quantity}"
            )
        
        # Determinar duración de reserva
        duration_minutes = 5 if purpose == "cliente" else 1
        expires_at = datetime.now() + timedelta(minutes=duration_minutes)
        
        # Crear reserva
        reservation = self.repository.create_product_reservation(
            reference_code=reference_code,
            size=size,
            quantity=quantity,
            user_id=user_id,
            location_id=location_id,
            purpose=purpose,
            expires_at=expires_at
        )
        
        return {
            "success": True,
            "reservation_id": reservation.id,
            "message": f"Producto reservado por {duration_minutes} minutos",
            "expires_at": expires_at.isoformat(),
            "duration_minutes": duration_minutes,
            "purpose": purpose
        }
    
    async def get_active_reservations(
        self,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtener reservas activas de un usuario
        """
        reservations = self.repository.get_active_reservations(user_id)
        
        result = []
        for reservation in reservations:
            time_left = reservation.expires_at - datetime.now()
            time_left_seconds = max(0, int(time_left.total_seconds()))
            
            result.append({
                "id": reservation.id,
                "sneaker_reference_code": reservation.sneaker_reference_code,
                "size": reservation.size,
                "quantity": reservation.quantity,
                "purpose": reservation.purpose,
                "reserved_at": reservation.reserved_at.isoformat(),
                "expires_at": reservation.expires_at.isoformat(),
                "time_left_seconds": time_left_seconds,
                "time_left_minutes": time_left_seconds / 60
            })
        
        return result
    
    async def release_reservation(
        self,
        reservation_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Liberar reserva manualmente
        """
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation or reservation.user_id != user_id:
            raise HTTPException(status_code=404, detail="Reserva no encontrada")
        
        if reservation.status != 'active':
            raise HTTPException(status_code=400, detail="La reserva ya no está activa")
        
        self.repository.release_reservation(reservation_id)
        
        return {
            "success": True,
            "message": "Reserva liberada exitosamente",
            "reservation_id": reservation_id
        }
    
    # ==================== DASHBOARD DEL VENDEDOR ====================
    
    async def get_vendor_dashboard(
        self,
        user_id: int,
        location_id: int
    ) -> VendorDashboardResponse:
        """
        Dashboard completo del vendedor
        """
        today = date.today()
        
        # Ventas del día
        sales_today = self.repository.get_sales_by_seller_and_date(
            user_id, location_id, today
        )
        confirmed_amount = sum(sale.total_amount for sale in sales_today if sale.confirmed)
        pending_amount = sum(sale.total_amount for sale in sales_today 
                           if sale.requires_confirmation and not sale.confirmed)
        
        # Gastos del día
        expenses_today = self.repository.get_expenses_by_user_and_date(
            user_id, location_id, today
        )
        total_expenses = sum(expense.amount for expense in expenses_today)
        
        # Reservas activas
        active_reservations = self.repository.get_active_reservations(user_id)
        
        # Solicitudes pendientes
        pending_discounts = self.repository.get_pending_discount_requests(user_id)
        
        return VendorDashboardResponse(
            success=True,
            dashboard_timestamp=datetime.now(),
            vendor_info={
                "user_id": user_id,
                "location_id": location_id,
                "location_name": f"Local #{location_id}"
            },
            today_summary={
                "date": today.isoformat(),
                "sales": {
                    "total_count": len(sales_today),
                    "confirmed_amount": float(confirmed_amount),
                    "pending_amount": float(pending_amount),
                    "total_amount": float(confirmed_amount + pending_amount)
                },
                "expenses": {
                    "count": len(expenses_today),
                    "total_amount": float(total_expenses)
                },
                "net_income": float(confirmed_amount - total_expenses),
                "active_reservations": len(active_reservations)
            },
            pending_actions={
                "pending_confirmations": len([s for s in sales_today 
                                            if s.requires_confirmation and not s.confirmed]),
                "pending_discount_requests": len(pending_discounts),
                "active_reservations": len(active_reservations)
            },
            quick_actions=[
                "Escanear nuevo producto",
                "Registrar venta",
                "Registrar gasto", 
                "Ver ventas del día",
                "Reservar producto"
            ]
        )