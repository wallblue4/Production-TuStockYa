# scripts/render_setup.py
"""
Script para ejecutar migraciones y setup inicial en Render
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext

def setup_database():
    """Setup inicial de la base de datos en Render"""
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ DATABASE_URL no encontrada")
        return False
    
    print("🔧 Configurando base de datos en Render...")
    
    try:
        # Conectar con SSL
        conn = psycopg2.connect(f"{DATABASE_URL}?sslmode=require")
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        print("✅ Conectado a PostgreSQL")
        
        # Verificar si necesitamos crear ubicación
        cursor.execute("SELECT COUNT(*) as count FROM locations")
        locations_count = cursor.fetchone()['count']
        
        if locations_count == 0:
            print("📍 Creando ubicación inicial...")
            cursor.execute("""
                INSERT INTO locations (name, type, address, is_active, created_at)
                VALUES ('Local Principal', 'local', 'Ubicación Principal', true, NOW())
                RETURNING id, name
            """)
            location = cursor.fetchone()
            location_id = location['id']
            print(f"✅ Ubicación creada: {location['name']}")
        else:
            cursor.execute("SELECT id FROM locations ORDER BY id LIMIT 1")
            location_id = cursor.fetchone()['id']
            print(f"📍 Usando ubicación existente: {location_id}")
        
        # Crear usuarios si no existen
        cursor.execute("SELECT COUNT(*) as count FROM users")
        users_count = cursor.fetchone()['count']
        
        if users_count == 0:
            print("👥 Creando usuarios iniciales...")
            
            users = [
                ("admin@tustockya.com", "admin123", "Admin", "Principal", "administrador"),
                ("vendedor@tustockya.com", "vendedor123", "Vendedor", "Demo", "vendedor"),
                ("bodeguero@tustockya.com", "bodeguero123", "Bodeguero", "Demo", "bodeguero"),
                ("corredor@tustockya.com", "corredor123", "Corredor", "Demo", "corredor")
            ]
            
            for email, password, first_name, last_name, role in users:
                password_hash = pwd_context.hash(password)
                cursor.execute("""
                    INSERT INTO users (email, password_hash, first_name, last_name, role, location_id, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, true, NOW())
                """, (email, password_hash, first_name, last_name, role, location_id))
                print(f"✅ Usuario creado: {email}")
        
        conn.commit()
        print("🎉 Setup completado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en setup: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    setup_database()