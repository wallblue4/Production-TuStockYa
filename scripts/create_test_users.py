"""
Script para crear usuarios de prueba
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config.settings import settings
from app.shared.database.models import User, Location
from app.core.auth.service import AuthService

# Crear engine y session
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_test_users():
    """Crear usuarios de prueba para cada rol"""
    
    db = SessionLocal()
    
    try:
        # Verificar si ya existen usuarios
        existing_users = db.query(User).count()
        if existing_users > 0:
            print(f"✅ Ya existen {existing_users} usuarios en la base de datos")
            return
        
        # Obtener ubicación por defecto (debería existir)
        location = db.query(Location).first()
        if not location:
            print("❌ No hay ubicaciones en la base de datos. Crear primero las ubicaciones.")
            return
        
        # Lista de usuarios de prueba
        test_users = [
            {
                "email": "boss@tustockya.com",
                "password": "boss123",
                "first_name": "Carlos",
                "last_name": "CEO",
                "role": "boss"
            },
            {
                "email": "admin@tustockya.com", 
                "password": "admin123",
                "first_name": "Ana",
                "last_name": "Administradora",
                "role": "administrador"
            },
            {
                "email": "vendedor@tustockya.com",
                "password": "vendedor123", 
                "first_name": "Juan",
                "last_name": "Vendedor",
                "role": "vendedor"
            },
            {
                "email": "bodeguero@tustockya.com",
                "password": "bodeguero123",
                "first_name": "María",
                "last_name": "Bodeguera", 
                "role": "bodeguero"
            },
            {
                "email": "corredor@tustockya.com",
                "password": "corredor123",
                "first_name": "Luis",
                "last_name": "Corredor",
                "role": "corredor"
            }
        ]
        
        # Crear usuarios
        for user_data in test_users:
            # Hash de la contraseña
            password_hash = AuthService.get_password_hash(user_data["password"])
            
            # Crear usuario
            user = User(
                email=user_data["email"],
                password_hash=password_hash,
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
                role=user_data["role"],
                location_id=location.id,
                is_active=True
            )
            
            db.add(user)
            print(f"✅ Usuario creado: {user_data['email']} / {user_data['password']} ({user_data['role']})")
        
        # Commit cambios
        db.commit()
        print(f"\n🎉 {len(test_users)} usuarios de prueba creados exitosamente!")
        print("\n📋 Credenciales de prueba:")
        for user_data in test_users:
            print(f"   👤 {user_data['role'].upper()}: {user_data['email']} / {user_data['password']}")
            
    except Exception as e:
        db.rollback()
        print(f"❌ Error creando usuarios: {e}")
        
    finally:
        db.close()

if __name__ == "__main__":
    create_test_users()