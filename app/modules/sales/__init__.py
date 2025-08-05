# app/modules/sales/__init__.py
"""
Módulo de Ventas - Funcionalidades del Vendedor

Este módulo implementa todas las funcionalidades requeridas para el rol de vendedor:

- VE001: Escaneo con IA y verificación de stock
- VE002: Registro de ventas completas  
- VE003: Consulta de productos por referencia
- VE004: Registro de gastos operativos
- VE005: Consulta de ventas del día
- VE007: Solicitudes de descuento
- VE016: Sistema de reservas automático
- VE018: Sugerencias de productos alternativos

Arquitectura:
- router.py: Endpoints FastAPI
- service.py: Lógica de negocio
- repository.py: Acceso a datos
- schemas.py: Modelos Pydantic de request/response
"""

from .router import router as sales_router
from .service import SalesService
from .repository import SalesRepository

__all__ = [
    "sales_router",
    "SalesService", 
    "SalesRepository"
]