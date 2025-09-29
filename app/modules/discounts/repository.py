# app/modules/discounts/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from app.shared.database.models import DiscountRequest, User

class DiscountsRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create_discount_request(self, seller_id: int, amount: Decimal, reason: str) -> DiscountRequest:
        """Crear nueva solicitud de descuento"""
        discount_request = DiscountRequest(
            seller_id=seller_id,
            amount=amount,
            reason=reason,
            status='pending',
            requested_at=datetime.now()
        )
        
        self.db.add(discount_request)
        self.db.commit()
        self.db.refresh(discount_request)
        
        return discount_request
    
    def get_discount_requests_by_seller(self, seller_id: int) -> List[Dict[str, Any]]:
        """Obtener solicitudes de descuento de un vendedor con info del admin"""
        # Query como en el backend antiguo
        query = self.db.query(
            DiscountRequest.id,
            DiscountRequest.seller_id,
            DiscountRequest.amount,
            DiscountRequest.reason,
            DiscountRequest.status,
            DiscountRequest.administrator_id,
            DiscountRequest.requested_at,
            DiscountRequest.reviewed_at,
            DiscountRequest.admin_comments,
            User.first_name.label('admin_first_name'),
            User.last_name.label('admin_last_name')
        ).outerjoin(
            User, DiscountRequest.administrator_id == User.id
        ).filter(
            DiscountRequest.seller_id == seller_id
        ).order_by(desc(DiscountRequest.requested_at))
        
        results = query.all()
        
        return [
            {
                "id": row.id,
                "seller_id": row.seller_id,
                "amount": float(row.amount),
                "reason": row.reason,
                "status": row.status,
                "administrator_id": row.administrator_id,
                "requested_at": row.requested_at.isoformat(),
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                "admin_comments": row.admin_comments,
                "admin_first_name": row.admin_first_name,
                "admin_last_name": row.admin_last_name,
                "admin_name": f"{row.admin_first_name} {row.admin_last_name}" if row.admin_first_name else None
            }
            for row in results
        ]
    
    def get_pending_discount_requests(self, seller_id: int) -> List[DiscountRequest]:
        """Obtener solicitudes pendientes del vendedor"""
        return self.db.query(DiscountRequest).filter(
            and_(
                DiscountRequest.seller_id == seller_id,
                DiscountRequest.status == 'pending'
            )
        ).all()
    
    def get_discount_requests_summary(self, seller_id: int) -> Dict[str, Any]:
        """Obtener resumen de solicitudes de descuento"""
        requests = self.get_discount_requests_by_seller(seller_id)
        
        summary = {
            "total_requests": len(requests),
            "pending": len([r for r in requests if r['status'] == 'pending']),
            "approved": len([r for r in requests if r['status'] == 'approved']),
            "rejected": len([r for r in requests if r['status'] == 'rejected']),
            "total_amount_requested": sum(r['amount'] for r in requests),
            "total_amount_approved": sum(r['amount'] for r in requests if r['status'] == 'approved'),
            "approval_rate": 0.0
        }
        
        if summary["total_requests"] > 0:
            summary["approval_rate"] = round(
                (summary["approved"] / summary["total_requests"]) * 100, 1
            )
        
        return summary