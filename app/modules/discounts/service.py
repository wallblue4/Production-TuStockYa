# app/modules/discounts/service.py
from typing import Dict, Any
from decimal import Decimal
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .repository import DiscountsRepository
from .schemas import DiscountRequestCreate, DiscountRequestResponse, MyDiscountRequestsResponse

class DiscountsService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = DiscountsRepository(db)
        self.MAX_DISCOUNT_AMOUNT = 5000  # Como en el backend antiguo
    
    async def create_discount_request(
        self,
        discount_data: DiscountRequestCreate,
        seller_id: int
    ) -> DiscountRequestResponse:
        """Crear solicitud de descuento"""
        
        # Validaciones como en el backend antiguo
        if discount_data.amount > self.MAX_DISCOUNT_AMOUNT:
            raise HTTPException(
                status_code=400,
                detail=f"El descuento máximo es de ${self.MAX_DISCOUNT_AMOUNT:,} pesos. Para descuentos mayores contacte al administrador directamente."
            )
        
        if discount_data.amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="El monto del descuento debe ser mayor a $0"
            )
        
        try:
            # Crear solicitud en BD
            discount_request = self.repository.create_discount_request(
                seller_id=seller_id,
                amount=discount_data.amount,
                reason=discount_data.reason
            )
            
            return DiscountRequestResponse(
                success=True,
                message="Solicitud de descuento enviada al administrador",
                discount_request_id=discount_request.id,
                amount=discount_request.amount,
                reason=discount_request.reason,
                status=discount_request.status,
                requested_at=discount_request.requested_at,
                seller_info={
                    "seller_id": seller_id
                },
                within_limit=discount_data.amount <= self.MAX_DISCOUNT_AMOUNT,
                max_allowed=self.MAX_DISCOUNT_AMOUNT
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creando solicitud: {str(e)}")
    
    async def get_my_discount_requests(self, seller_id: int) -> MyDiscountRequestsResponse:
        """Obtener mis solicitudes de descuento"""
        requests = self.repository.get_discount_requests_by_seller(seller_id)
        summary = self.repository.get_discount_requests_summary(seller_id)
        
        return MyDiscountRequestsResponse(
            success=True,
            message="Solicitudes de descuento obtenidas",
            requests=requests,
            summary=summary,
            seller_info={
                "seller_id": seller_id,
                "can_request_more": True,  # Siempre puede solicitar más
                "max_amount_per_request": self.MAX_DISCOUNT_AMOUNT
            }
        )