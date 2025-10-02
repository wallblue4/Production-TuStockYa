from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.service import AuthService
from app.core.auth.schemas import UserLogin, TokenResponse, UserResponse
from app.shared.database.models import User
from app.core.auth.dependencies import get_current_user 

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Endpoint de login para obtener token de acceso
    
    **Parámetros:**
    - **username**: Email del usuario
    - **password**: Contraseña del usuario
    
    **Returns:**
    - Token de acceso JWT
    - Información del usuario
    """
    
    # Buscar usuario por email
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verificar contraseña
    if not AuthService.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verificar que el usuario esté activo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    
    # Crear token de acceso
    access_token = AuthService.create_access_token(
        data={
            "user_id": user.id,
            "email": user.email,
            "role": user.role
        }
    )
    
    # Obtener información de ubicación si existe
    location_name = None
    if user.location:
        location_name = user.location.name
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            location_id=user.location_id,
            location_name=location_name,
            is_active=user.is_active
        )
    )

@router.post("/login-json", response_model=TokenResponse)
async def login_json(
    user_login: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Endpoint de login alternativo que acepta JSON
    
    **Body:**
    ```json
    {
        "email": "user@example.com",
        "password": "password123"
    }
    ```
    """
    
    # Buscar usuario por email
    user = db.query(User).filter(User.email == user_login.email).first()
    
    if not user or not AuthService.verify_password(user_login.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    
    # Crear token
    access_token = AuthService.create_access_token(
        data={
            "user_id": user.id,
            "email": user.email,
            "role": user.role
        }
    )
    
    # Obtener información de ubicación
    location_name = None
    if user.location:
        location_name = user.location.name
    
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            location_id=user.location_id,
            location_name=location_name,
            is_active=user.is_active
        )
    )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Obtener información del usuario actual
    
    **Headers requeridos:**
    - Authorization: Bearer {token}
    """
    
    location_name = None
    if current_user.location:
        location_name = current_user.location.name
    
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role,
        location_id=current_user.location_id,
        location_name=location_name,
        is_active=current_user.is_active
    )

@router.post("/logout")
async def logout():
    """
    Logout (con JWT stateless, solo informativo)
    
    En el frontend debes eliminar el token del storage.
    """
    return {"message": "Logout exitoso. Elimina el token del cliente."}

# Endpoint para verificar roles (útil para debugging)
@router.get("/check-permissions")
async def check_permissions(
    current_user: User = Depends(get_current_user)
):
    """Verificar permisos del usuario actual"""
    
    permissions = {
        "seller": ["scan", "sell", "expenses", "transfers"],
        "bodeguero": ["inventory", "transfers", "warehouse"],
        "corredor": ["transport", "deliveries"],
        "administrador": ["all_operations", "user_management"],
        "boss": ["all_permissions", "executive_dashboard"]
    }
    
    user_permissions = permissions.get(current_user.role, [])
    
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role,
            "full_name": current_user.full_name
        },
        "permissions": user_permissions,
        "can_access": {
            "sales_module": current_user.role in ["seller", "administrador", "boss"],
            "warehouse_module": current_user.role in ["bodeguero", "administrador", "boss"],
            "logistics_module": current_user.role in ["corredor", "administrador", "boss"],
            "admin_panel": current_user.role in ["administrador", "boss"],
            "executive_dashboard": current_user.role == "boss"
        }
    }