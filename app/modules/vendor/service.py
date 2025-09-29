# app/modules/vendor/service.py
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from .repository import VendorRepository
from .schemas import VendorDashboardResponse, TransferSummaryResponse, CompletedTransfersResponse

class VendorService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = VendorRepository(db)
    
    async def get_dashboard(self, user_id: int, user_info: Dict[str, Any]) -> VendorDashboardResponse:
        """Dashboard completo del vendedor - igual estructura que backend antiguo"""
        
        # Obtener todos los datos necesarios
        sales_today = self.repository.get_sales_summary_today(user_id)
        payment_methods = self.repository.get_payment_methods_breakdown_today(user_id)
        expenses_today = self.repository.get_expenses_summary_today(user_id)
        transfer_stats = self.repository.get_transfer_requests_stats(user_id)
        discount_stats = self.repository.get_discount_requests_stats(user_id)
        unread_returns = self.repository.get_unread_return_notifications(user_id)
        
        # Calcular ingreso neto
        net_income = sales_today['confirmed_amount'] - expenses_today['total']
        
        # Estructura exacta como el backend antiguo
        return VendorDashboardResponse(
            success=True,
            message="Dashboard del vendedor",
            dashboard_timestamp=datetime.now(),
            vendor_info={
                "name": f"{user_info['first_name']} {user_info['last_name']}",
                "email": user_info['email'],
                "role": user_info['role'],
                "location_id": user_info['location_id'],
                "location_name": f"Local #{user_info['location_id']}"
            },
            today_summary={
                "date": datetime.now().date().isoformat(),
                "sales": {
                    "total_count": sales_today['total_sales'],
                    "confirmed_amount": sales_today['confirmed_amount'],
                    "pending_amount": sales_today['pending_amount'],
                    "pending_confirmations": sales_today['pending_confirmations'],
                    "total_amount": sales_today['confirmed_amount'] + sales_today['pending_amount']
                },
                "payment_methods_breakdown": payment_methods,
                "expenses": {
                    "count": expenses_today['count'],
                    "total_amount": expenses_today['total']
                },
                "net_income": net_income
            },
            pending_actions={
                "sale_confirmations": sales_today['pending_confirmations'],
                "transfer_requests": {
                    "pending": transfer_stats['pending'],
                    "in_transit": transfer_stats['in_transit'],
                    "delivered": transfer_stats['delivered']
                },
                "discount_requests": {
                    "pending": discount_stats['pending'],
                    "approved": discount_stats['approved'],
                    "rejected": discount_stats['rejected']
                },
                "return_notifications": unread_returns
            },
            quick_actions=[
                "Escanear nuevo tenis",
                "Registrar venta",
                "Registrar gasto",
                "Solicitar transferencia",
                "Ver ventas del día",
                "Ver gastos del día"
            ]
        )
    
    async def get_pending_transfers(self, user_id: int) -> TransferSummaryResponse:
        """Obtener transferencias pendientes para el vendedor"""
        pending_transfers = self.repository.get_pending_transfers_for_vendor(user_id)
        
        # Contar por urgencia
        urgent_count = len([t for t in pending_transfers if t['priority'] == 'high'])
        normal_count = len([t for t in pending_transfers if t['priority'] == 'normal'])
        
        return TransferSummaryResponse(
            success=True,
            message="Transferencias pendientes de confirmación",
            pending_transfers=pending_transfers,
            urgent_count=urgent_count,
            normal_count=normal_count,
            total_pending=len(pending_transfers),
            summary={
                "total_transfers": len(pending_transfers),
                "requiring_confirmation": len(pending_transfers),
                "urgent_items": urgent_count,
                "normal_items": normal_count
            },
            attention_needed=[
                transfer for transfer in pending_transfers 
                if transfer['priority'] == 'high'
            ]
        )
    
    async def get_completed_transfers(self, user_id: int) -> CompletedTransfersResponse:
        """Obtener transferencias completadas del día"""
        completed_transfers = self.repository.get_completed_transfers_today(user_id)
        
        # Calcular estadísticas del día
        total_transfers = len(completed_transfers)
        completed_count = len([t for t in completed_transfers if t['status'] == 'completed'])
        cancelled_count = len([t for t in completed_transfers if t['status'] == 'cancelled'])
        success_rate = (completed_count / total_transfers * 100) if total_transfers > 0 else 0
        
        return CompletedTransfersResponse(
            success=True,
            message="Transferencias completadas del día",
            date=datetime.now().date().isoformat(),
            completed_transfers=completed_transfers,
            today_stats={
                "total_transfers": total_transfers,
                "completed": completed_count,
                "cancelled": cancelled_count,
                "success_rate": round(success_rate, 1),
                "average_duration": "2.3h",  # Calcular real si es necesario
                "performance": "Buena" if success_rate >= 80 else "Regular"
            }
        )