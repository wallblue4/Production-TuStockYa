# app/modules/vendor/__init__.py
"""
Módulo Vendor - Dashboard y Operaciones del Vendedor

Este módulo proporciona la vista consolidada del vendedor:
- Dashboard con métricas del día
- Transferencias pendientes y completadas
- Confirmación de recepciones
- Agregación de datos de otros módulos

Arquitectura:
- router.py: Endpoints específicos del vendedor
- service.py: Lógica de agregación de datos
- repository.py: Queries específicas del vendedor
- schemas.py: Modelos de dashboard y transferencias
"""

from .router import router
from .service import VendorService
from .repository import VendorRepository

__all__ = [
    "router",
    "VendorService", 
    "VendorRepository"
]