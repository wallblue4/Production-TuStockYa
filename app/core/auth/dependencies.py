from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.shared.database.models import User
from app.core.auth.service import AuthService

security = HTTPBearer()

class AuthenticationError(HTTPException):
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

class AuthorizationError(HTTPException):
    def __init__(self, detail: str = "Not enough permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Obtener usuario actual desde el token"""
    
    # Verificar token
    payload = AuthService.verify_token(credentials.credentials)
    if payload is None:
        raise AuthenticationError("Token inválido o expirado")
    
    # Obtener user_id del payload
    user_id: int = payload.get("user_id")
    if user_id is None:
        raise AuthenticationError("Payload del token inválido")
    
    # Buscar usuario en base de datos con relaciones
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )
    
    if user is None:
        raise AuthenticationError("Usuario no encontrado")
    
    if not user.is_active:
        raise AuthenticationError("Usuario inactivo")
    
    return user

def require_roles(allowed_roles: List[str]):
    """Factory para crear dependency que requiere roles específicos"""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise AuthorizationError(
                f"Rol '{current_user.role}' no autorizado. Roles permitidos: {allowed_roles}"
            )
        return current_user
    return role_checker

# Dependencies específicas por rol
def get_seller_user(current_user: User = Depends(require_roles(["seller", "administrador", "boss"]))):
    """Dependency para vendedores"""
    return current_user

def get_warehouse_user(current_user: User = Depends(require_roles(["bodeguero", "administrador", "boss"]))):
    """Dependency para bodegueros"""
    return current_user

def get_courier_user(current_user: User = Depends(require_roles(["corredor", "administrador", "boss"]))):
    """Dependency para corredores"""
    return current_user

def get_admin_user(current_user: User = Depends(require_roles(["administrador", "boss"]))):
    """Dependency para administradores"""
    return current_user

def get_boss_user(current_user: User = Depends(require_roles(["boss"]))):
    """Dependency para boss"""
    return current_user

# Utility functions para verificación de permisos
def can_access_location(user: User, location_id: int) -> bool:
    """Verificar si usuario puede acceder a una ubicación específica"""
    
    # Boss y admin pueden acceder a todo
    if user.role in ["boss", "administrador"]:
        return True
    
    # Otros roles solo pueden acceder a su ubicación asignada
    return user.location_id == location_id

def can_manage_user(current_user: User, target_user: User) -> bool:
    """Verificar si usuario puede gestionar a otro usuario"""
    
    # Boss puede gestionar a todos
    if current_user.role == "boss":
        return True
    
    # Administrador puede gestionar vendedores, bodegueros y corredores
    if current_user.role == "administrador":
        return target_user.role in ["seller", "bodeguero", "corredor"]
    
    # Otros roles no pueden gestionar usuarios
    return False

def verify_location_access(location_id: int):
    """Factory para verificar acceso a ubicación específica"""
    def location_checker(current_user: User = Depends(get_current_user)):
        if not can_access_location(current_user, location_id):
            raise AuthorizationError(
                f"No tienes permisos para acceder a la ubicación {location_id}"
            )
        return current_user
    return location_checker