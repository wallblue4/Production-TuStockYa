# app/modules/courier/__init__.py
"""
Módulo Courier - Operaciones de Corredor

Este módulo implementa el flujo completo del corredor:
- CO001: Recibir notificaciones de solicitudes de transporte
- CO002: Aceptar solicitud e iniciar recorrido
- CO003: Confirmar recolección
- CO004: Confirmar entrega
- CO005: Reportar incidencias durante el transporte
- CO006: Historial de entregas

Arquitectura:
- router.py: Endpoints del corredor
- service.py: Lógica de negocio de courier
- repository.py: Acceso a datos de courier
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import CourierService
from .repository import CourierRepository

__all__ = [
    "router",
    "CourierService", 
    "CourierRepository"
]