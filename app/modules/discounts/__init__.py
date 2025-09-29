# app/modules/discounts/__init__.py
"""
Módulo de Descuentos - Solicitudes de Descuento

Este módulo maneja las solicitudes de descuento de los vendedores:
- VE007: Solicitar descuentos hasta $5,000
- Sistema de aprobación administrativa
- Tracking de estado de solicitudes
- Estadísticas de aprobación

Arquitectura:
- router.py: Endpoints de descuentos
- service.py: Lógica de negocio de descuentos
- repository.py: Acceso a datos de descuentos
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import DiscountsService
from .repository import DiscountsRepository

__all__ = [
    "router",
    "DiscountsService", 
    "DiscountsRepository"
]