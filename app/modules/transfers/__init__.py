"""
Módulo de Transferencias - TuStockYa

Este módulo maneja todo el flujo de transferencias de productos entre ubicaciones,
incluyendo la lógica para vendedores, bodegueros y corredores.

Funcionalidades principales:
- VE003: Solicitud de productos entre ubicaciones
- VE008: Confirmación de recepción con actualización automática de inventario
- BG001-BG003: Flujo completo de bodeguero
- CO001-CO007: Flujo completo de corredor

Requerimientos implementados:
- Sistema de prioridades (cliente presente vs restock)
- Actualización automática de inventario
- Tracking completo con timestamps
- Manejo de excepciones y reversión automática
- Dashboard personalizado por rol
"""

from .router import router
from .service import TransferService
from .repository import TransferRepository
from .schemas import (
    TransferRequestCreate,
    TransferRequestResponse,
    TransferStatus,
    Purpose,
    TransferDashboard
)

__all__ = [
    "router",
    "TransferService", 
    "TransferRepository",
    "TransferRequestCreate",
    "TransferRequestResponse", 
    "TransferStatus",
    "Purpose",
    "TransferDashboard"
]