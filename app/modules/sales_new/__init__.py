# app/modules/sales_new/__init__.py
"""
Módulo de Ventas - Gestión Completa de Ventas

Este módulo maneja el ciclo completo de ventas incluyendo:
- VE002: Registro de ventas completas
- VE005: Consulta de ventas del día
- Confirmación de ventas
- Actualización automática de inventario

Arquitectura:
- router.py: Endpoints de ventas
- service.py: Lógica de negocio de ventas
- repository.py: Acceso a datos de ventas
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import SalesService
from .repository import SalesRepository

__all__ = [
    "router",
    "SalesService", 
    "SalesRepository"
]# app/modules/sales_new/__init__.py
"""
Módulo de Ventas - Gestión Completa de Ventas

Este módulo maneja el ciclo completo de ventas incluyendo:
- VE002: Registro de ventas completas
- VE005: Consulta de ventas del día
- Confirmación de ventas
- Actualización automática de inventario

Arquitectura:
- router.py: Endpoints de ventas
- service.py: Lógica de negocio de ventas
- repository.py: Acceso a datos de ventas
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import SalesService
from .repository import SalesRepository

__all__ = [
    "router",
    "SalesService", 
    "SalesRepository"
]