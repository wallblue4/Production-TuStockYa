# app/modules/expenses/__init__.py
"""
Módulo de Gastos - Gestión de Gastos Operativos

Este módulo maneja los gastos operativos diarios de los vendedores:
- VE004: Registro de gastos operativos
- Comprobantes digitales
- Categorización de gastos
- Resúmenes diarios

Arquitectura:
- router.py: Endpoints de gastos
- service.py: Lógica de negocio de gastos
- repository.py: Acceso a datos de gastos
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import ExpensesService
from .repository import ExpensesRepository

__all__ = [
    "router",
    "ExpensesService", 
    "ExpensesRepository"
]