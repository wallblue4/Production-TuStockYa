from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserLogin(BaseModel):
    """Schema para login de usuario"""
    email: str = Field(..., description="Email del usuario")
    password: str = Field(..., min_length=6, description="Contraseña del usuario")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "vendedor@tustockya.com",
                "password": "vendedor123"
            }
        }

class UserResponse(BaseModel):
    """Schema para respuesta de usuario"""
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    is_active: bool
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "email": "vendedor@tustockya.com",
                "first_name": "Juan",
                "last_name": "Pérez",
                "role": "seller",
                "location_id": 1,
                "location_name": "Local Principal",
                "is_active": True
            }
        }

class TokenResponse(BaseModel):
    """Schema para respuesta de token"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": 1,
                    "email": "vendedor@tustockya.com",
                    "first_name": "Juan",
                    "last_name": "Pérez",
                    "role": "seller",
                    "location_id": 1,
                    "location_name": "Local Principal",
                    "is_active": True
                }
            }
        }

class TokenPayload(BaseModel):
    """Schema para payload del token"""
    user_id: int
    email: str
    role: str
    exp: Optional[datetime] = None

class ChangePasswordRequest(BaseModel):
    """Schema para cambio de contraseña"""
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)
    
    def passwords_match(self) -> bool:
        return self.new_password == self.confirm_password

class UserCreateRequest(BaseModel):
    """Schema para crear usuario (admin only)"""
    email: str = Field(..., description="Email del usuario")
    password: str = Field(..., min_length=6)
    first_name: str = Field(..., min_length=2)
    last_name: str = Field(..., min_length=2)
    role: str = Field(..., pattern="^(seller|bodeguero|corredor|administrador|boss)$")
    location_id: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "nuevo@tustockya.com",
                "password": "password123",
                "first_name": "María",
                "last_name": "García",
                "role": "seller",
                "location_id": 1
            }
        }