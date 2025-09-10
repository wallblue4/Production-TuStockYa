from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any, Optional, Set
from decimal import Decimal
from .repository import CostRepository

class CostCalculatorService:
    """Servicio para calcular vencimientos de costos dinámicamente"""
    
    def __init__(self, repository: CostRepository):
        self.repository = repository
    
    def calculate_due_payments(
        self, 
        cost_config_id: int, 
        from_date: date, 
        to_date: date
    ) -> List[Dict[str, Any]]:
        """Calcular vencimientos de pago para un rango de fechas"""
        
        # 1. Obtener configuración
        config = self.repository.get_cost_configuration_by_id(cost_config_id)
        if not config or not config["is_active"]:
            return []
        
        # 2. Obtener pagos ya realizados
        paid_payments = self.repository.get_paid_payments_for_config(
            cost_config_id, from_date, to_date
        )
        paid_dates = {p["due_date"] for p in paid_payments}
        
        # 3. Obtener excepciones
        exceptions = self.repository.get_payment_exceptions_for_config(
            cost_config_id, from_date, to_date
        )
        exception_map = {e["exception_date"]: e for e in exceptions}
        
        # 4. Calcular fechas teóricas de vencimiento
        theoretical_dates = self._calculate_theoretical_dates(config, from_date, to_date)
        
        # 5. Construir lista de pagos pendientes aplicando excepciones
        due_payments = []
        for due_date in theoretical_dates:
            # Verificar si ya está pagado
            if due_date in paid_dates:
                continue
            
            # Aplicar excepciones
            payment_amount = config["amount"]
            actual_due_date = due_date
            
            if due_date in exception_map:
                exception = exception_map[due_date]
                if exception["exception_type"] == "skip":
                    continue  # Saltar este pago
                elif exception["exception_type"] == "different_amount":
                    payment_amount = exception["new_amount"] or config["amount"]
                elif exception["exception_type"] == "postponed":
                    actual_due_date = exception["new_due_date"] or due_date
                    payment_amount = exception["new_amount"] or config["amount"]
            
            # Calcular estado del pago
            status, days_difference = self._calculate_payment_status(actual_due_date)
            
            due_payments.append({
                "cost_configuration_id": cost_config_id,
                "due_date": actual_due_date,
                "amount": payment_amount,
                "status": status,
                "days_difference": days_difference,
                "cost_type": config["cost_type"],
                "description": config["description"],
                "frequency": config["frequency"],
                "is_paid": False
            })
        
        return sorted(due_payments, key=lambda x: x["due_date"])
    
    def _calculate_theoretical_dates(
        self, 
        config: Dict[str, Any], 
        from_date: date, 
        to_date: date
    ) -> List[date]:
        """Calcular fechas teóricas de vencimiento según frecuencia"""
        
        frequency = config["frequency"]
        start_date = max(config["start_date"], from_date)
        end_date = min(config.get("end_date") or date(2030, 12, 31), to_date)
        
        # Mapeo de frecuencias a deltas
        frequency_deltas = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "monthly": relativedelta(months=1),
            "quarterly": relativedelta(months=3),
            "annual": relativedelta(years=1)
        }
        
        delta = frequency_deltas.get(frequency)
        if not delta:
            return []
        
        dates = []
        current_date = start_date
        max_iterations = 2000  # Protección contra loops infinitos
        iteration = 0
        
        while current_date <= end_date and iteration < max_iterations:
            if current_date >= from_date:
                dates.append(current_date)
            
            # Avanzar fecha según tipo de delta
            if isinstance(delta, timedelta):
                current_date += delta
            else:  # relativedelta
                current_date += delta
            
            iteration += 1
        
        return dates
    
    def _calculate_payment_status(self, due_date: date) -> tuple[str, int]:
        today = date.today()
        
        if due_date < today:
            days_difference = (today - due_date).days
            return "overdue", days_difference
        elif due_date == today:
            return "overdue", 0  
        elif due_date <= today + timedelta(days=30):
            days_difference = (due_date - today).days
            return "upcoming", days_difference
        else:
            days_difference = (due_date - today).days
            return "pending", days_difference
    
    def calculate_dashboard_data(self, location_id: int) -> Dict[str, Any]:
        """Calcular datos completos para dashboard de una ubicación"""
        
        # Obtener configuraciones activas
        active_configs = self.repository.get_active_cost_configurations(location_id)
        
        today = date.today()
        
        # Rango de cálculo: 1 año atrás + 3 meses adelante
        past_date = today - timedelta(days=365)
        future_date = today + timedelta(days=90)
        
        # Preparar estructura del dashboard
        dashboard = {
            "location_id": location_id,
            "location_name": "",
            "total_monthly_costs": Decimal('0'),
            "pending_payments": [],
            "overdue_payments": [],
            "upcoming_payments": [],
            "paid_this_month": Decimal('0'),
            "pending_this_month": Decimal('0'),
            "overdue_amount": Decimal('0'),
            "total_configurations": len(active_configs),
            "active_configurations": len([c for c in active_configs if c.get("is_active")]),
            "next_payment_date": None
        }
        
        if not active_configs:
            return dashboard
        
        dashboard["location_name"] = active_configs[0]["location_name"]
        
        # Calcular costos mensuales estimados
        for config in active_configs:
            monthly_equivalent = self._calculate_monthly_equivalent(
                config["amount"], config["frequency"]
            )
            dashboard["total_monthly_costs"] += monthly_equivalent
        
        # Calcular pagos del mes actual
        month_start = today.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
        
        dashboard["paid_this_month"] = self.repository.get_paid_amount_for_month(
            location_id, month_start, month_end
        )
        
        # Procesar cada configuración
        next_payment_dates = []
        
        for config in active_configs:
            due_payments = self.calculate_due_payments(
                config["id"], past_date, future_date
            )
            
            for payment in due_payments:
                if payment["status"] == "overdue":
                    dashboard["overdue_payments"].append(payment)
                    dashboard["overdue_amount"] += payment["amount"]
                elif payment["status"] == "upcoming":
                    dashboard["upcoming_payments"].append(payment)
                elif payment["status"] == "pending":
                    dashboard["pending_payments"].append(payment)
                
                # Calcular pendientes del mes
                if (month_start <= payment["due_date"] <= month_end and 
                    payment["status"] in ["pending", "upcoming"]):
                    dashboard["pending_this_month"] += payment["amount"]
                
                # Recopilar fechas para próximo pago
                if payment["due_date"] >= today:
                    next_payment_dates.append(payment["due_date"])
        
        # Determinar próximo pago
        if next_payment_dates:
            dashboard["next_payment_date"] = min(next_payment_dates)
        
        # Ordenar listas por fecha
        dashboard["overdue_payments"].sort(key=lambda x: x["due_date"])
        dashboard["upcoming_payments"].sort(key=lambda x: x["due_date"])
        dashboard["pending_payments"].sort(key=lambda x: x["due_date"])
        
        return dashboard
    
    def _calculate_monthly_equivalent(self, amount: Decimal, frequency: str) -> Decimal:
        """Calcular equivalente mensual de un costo según frecuencia"""
        
        frequency_multipliers = {
            "daily": 30,      # 30 días aprox por mes
            "weekly": 4.33,   # 52 semanas / 12 meses
            "monthly": 1,
            "quarterly": 1/3, # 4 trimestres / 12 meses  
            "annual": 1/12    # 1 año / 12 meses
        }
        
        multiplier = frequency_multipliers.get(frequency, 1)
        return amount * Decimal(str(multiplier))
    
    def calculate_operational_dashboard(self, admin_id: int) -> Dict[str, Any]:
        """Calcular dashboard operativo consolidado"""
        
        # Obtener ubicaciones gestionadas
        managed_locations = self.repository.get_managed_locations_for_admin(admin_id)
        
        dashboard = {
            "summary": {
                "total_locations": len(managed_locations),
                "total_overdue_amount": Decimal('0'),
                "total_upcoming_amount": Decimal('0'),
                "critical_alerts_count": 0
            },
            "locations_status": [],
            "critical_alerts": [],
            "upcoming_week": [],
            "monthly_summary": {
                "total_monthly_costs": Decimal('0'),
                "total_paid_this_month": Decimal('0'),
                "total_pending_this_month": Decimal('0')
            }
        }
        
        today = date.today()
        next_week = today + timedelta(days=7)
        
        for location in managed_locations:
            # Calcular dashboard individual
            location_dashboard = self.calculate_dashboard_data(location["id"])
            
            # Estado de la ubicación
            location_status = {
                "location_id": location["id"],
                "location_name": location["name"],
                "monthly_costs": location_dashboard["total_monthly_costs"],
                "overdue_amount": location_dashboard["overdue_amount"],
                "overdue_count": len(location_dashboard["overdue_payments"]),
                "upcoming_count": len(location_dashboard["upcoming_payments"]),
                "status": "ok" if location_dashboard["overdue_amount"] == 0 else "attention"
            }
            dashboard["locations_status"].append(location_status)
            
            # Acumular totales
            dashboard["summary"]["total_overdue_amount"] += location_dashboard["overdue_amount"]
            dashboard["monthly_summary"]["total_monthly_costs"] += location_dashboard["total_monthly_costs"]
            dashboard["monthly_summary"]["total_paid_this_month"] += location_dashboard["paid_this_month"]
            dashboard["monthly_summary"]["total_pending_this_month"] += location_dashboard["pending_this_month"]
            
            # Alertas críticas (más de 7 días vencidos)
            for payment in location_dashboard["overdue_payments"]:
                if payment["days_difference"] > 7:
                    dashboard["summary"]["critical_alerts_count"] += 1
                    dashboard["critical_alerts"].append({
                        "location_name": location["name"],
                        "cost_type": payment["cost_type"],
                        "amount": payment["amount"],
                        "days_overdue": payment["days_difference"],
                        "priority": "high" if payment["days_difference"] > 15 else "medium",
                        "due_date": payment["due_date"]
                    })
            
            # Próximos vencimientos (7 días)
            for payment in location_dashboard["upcoming_payments"]:
                if payment["due_date"] <= next_week:
                    dashboard["upcoming_week"].append({
                        "location_name": location["name"],
                        "cost_type": payment["cost_type"],
                        "amount": payment["amount"],
                        "due_date": payment["due_date"],
                        "days_until_due": payment["days_difference"]
                    })
        
        # Ordenar alertas por criticidad
        dashboard["critical_alerts"].sort(
            key=lambda x: (x["priority"] == "high", x["days_overdue"]), 
            reverse=True
        )
        
        # Ordenar próximos por fecha
        dashboard["upcoming_week"].sort(key=lambda x: x["due_date"])
        
        return dashboard