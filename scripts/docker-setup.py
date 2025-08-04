#!/usr/bin/env python3
"""
Script para configurar base de datos en Docker
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext
import time
import sys

def wait_for_db():
    """Esperar que PostgreSQL esté listo"""
    DATABASE_URL = "postgresql://tustockya_user:tustockya_password_2024@localhost:5432/tustockya"
    
    print("⏳ Esperando que PostgreSQL esté listo...")
    
    for attempt in range(30):  # 30 intentos = 30 segundos
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.close()
            print("✅ PostgreSQL listo!")
            return True
        except psycopg2.OperationalError:
            print(f"⏳ Intento {attempt + 1}/30...")
            time.sleep(1)
    
    print("❌ PostgreSQL no está disponible después de 30 segundos")
    return False

def create_tables():
    """Crear tablas usando el esquema que ya tienes"""
    DATABASE_URL = "postgresql://tustockya_user:tustockya_password_2024@localhost:5432/tustockya"
    
    # Tu esquema SQL actual (del documento que compartiste)
    schema_sql = """
    -- Tu esquema completo aquí
    CREATE TABLE IF NOT EXISTS locations (
        id serial4 NOT NULL,
        "name" varchar(255) NOT NULL,
        "type" varchar(50) NOT NULL,
        address text NULL,
        phone varchar(50) NULL,
        is_active bool DEFAULT true NULL,
        created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
        CONSTRAINT locations_pkey PRIMARY KEY (id)
    );

    CREATE TABLE IF NOT EXISTS users (
        id serial4 NOT NULL,
        email varchar(255) NOT NULL,
        password_hash varchar(255) NOT NULL,
        first_name varchar(255) NOT NULL,
        last_name varchar(255) NOT NULL,
        "role" varchar(50) DEFAULT 'vendedor'::character varying NOT NULL,
        location_id int4 NULL,
        is_active bool DEFAULT true NULL,
        created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
        CONSTRAINT users_email_key UNIQUE (email),
        CONSTRAINT users_pkey PRIMARY KEY (id),
        CONSTRAINT users_location_id_fkey FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    
    -- Agregar aquí el resto de tu esquema...
    """
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("🏗️ Creando tablas...")
        cursor.execute(schema_sql)
        conn.commit()
        
        print("✅ Tablas creadas exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def create_test_users():
    """Crear usuarios de prueba"""
    DATABASE_URL = "postgresql://tustockya_user:tustockya_password_2024@localhost:5432/tustockya"
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Crear ubicación
        cursor.execute("""
            INSERT INTO locations (name, type, address, is_active, created_at)
            VALUES ('Local Principal', 'local', 'Calle Principal 123', true, NOW())
            ON CONFLICT DO NOTHING
            RETURNING id, name
        """)
        
        result = cursor.fetchone()
        if result:
            location_id = result['id']
            print(f"📍 Ubicación creada: {result['name']}")
        else:
            cursor.execute("SELECT id, name FROM locations ORDER BY id LIMIT 1")
            location = cursor.fetchone()
            location_id = location['id']
            print(f"📍 Usando ubicación existente: {location['name']}")
        
        # Usuarios de prueba
        users = [
            ("boss@tustockya.com", "boss123", "Carlos", "Jefe", "boss"),
            ("admin@tustockya.com", "admin123", "Ana", "Admin", "administrador"),
            ("vendedor@tustockya.com", "vendedor123", "Juan", "Vendedor", "vendedor"),
            ("bodeguero@tustockya.com", "bodeguero123", "Pedro", "Bodeguero", "bodeguero"),
            ("corredor@tustockya.com", "corredor123", "Luis", "Corredor", "corredor")
        ]
        
        created = 0
        for email, password, first_name, last_name, role in users:
            # Verificar si existe
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                continue
            
            # Crear usuario
            password_hash = pwd_context.hash(password)
            cursor.execute("""
                INSERT INTO users (email, password_hash, first_name, last_name, role, location_id, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, true, NOW())
            """, (email, password_hash, first_name, last_name, role, location_id))
            
            created += 1
            print(f"✅ Usuario: {email} / {password} ({role})")
        
        conn.commit()
        print(f"🎉 {created} usuarios creados")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creando usuarios: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    print("🚀 Configurando TuStockYa con Docker...")
    
    if not wait_for_db():
        sys.exit(1)
    
    if not create_tables():
        sys.exit(1)
    
    if not create_test_users():
        sys.exit(1)
    
    print("✅ Configuración completada!")
    print("\n📋 Credenciales de prueba:")
    print("   👤 BOSS: boss@tustockya.com / boss123")
    print("   👤 ADMIN: admin@tustockya.com / admin123") 
    print("   👤 VENDEDOR: vendedor@tustockya.com / vendedor123")
    print("   👤 BODEGUERO: bodeguero@tustockya.com / bodeguero123")
    print("   👤 CORREDOR: corredor@tustockya.com / corredor123")
    print("\n🌐 Servicios disponibles:")
    print("   📱 API: http://localhost:8000")
    print("   📚 Docs: http://localhost:8000/docs")
    print("   🗄️ Adminer: http://localhost:8080")

if __name__ == "__main__":
    main()