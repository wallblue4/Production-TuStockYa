# app/modules/classification/__init__.py
"""
Módulo de Clasificación - Escaneo con IA

Este módulo maneja el escaneo de productos usando IA y verificación de inventario.

Funcionalidades:
- VE001: Escaneo con IA y verificación de stock
- Integración con microservicio de clasificación
- Búsqueda en inventario local
- Sugerencias de transferencia
"""

from .router import router
from .service import ClassificationService
from .repository import ClassificationRepository

__all__ = [
    "router",
    "ClassificationService", 
    "ClassificationRepository"
]