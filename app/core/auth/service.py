from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config.settings import settings

# Password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    """Servicio de autenticación"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verificar contraseña"""
        try:
            # Ensure password is UTF-8 encoded and truncated if needed
            encoded_password = plain_password.encode('utf-8')[:72].decode('utf-8')
            return pwd_context.verify(encoded_password, hashed_password)
        except Exception as e:
            print(f"Password verification error: {str(e)}")
            return False
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generar hash de contraseña"""
        # Ensure password is UTF-8 encoded and truncated if needed
        encoded_password = password.encode('utf-8')[:72].decode('utf-8')
        return pwd_context.hash(encoded_password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Crear token de acceso"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Verificar y decodificar token"""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            return payload
        except JWTError:
            return None