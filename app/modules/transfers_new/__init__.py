# app/modules/transfers_new/__init__.py
"""
Módulo de Transferencias - Sistema de Transferencias entre Ubicaciones

Este módulo maneja el flujo completo de transferencias de productos:
- VE003: Solicitud de productos entre ubicaciones
- VE008: Confirmación de recepción con actualización automática de inventario
- Sistema de prioridades por propósito
- Tracking completo de estado

Arquitectura:
- router.py: Endpoints de transferencias
- service.py: Lógica de negocio de transferencias
- repository.py: Acceso a datos de transferencias
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import TransfersService
from .repository import TransfersRepository

__all__ = [
    "router",
    "TransfersService", 
    "TransfersRepository"
]