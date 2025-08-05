#!/usr/bin/env python3
"""
Script para crear SOLO usuarios de prueba en BD existente
NO crea tablas, solo usuarios
"""
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext

def main():
    print("👥 Creando usuarios de prueba en BD existente...")
    
    # Obtener URL de base de datos existente
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL no configurada")
        print("💡 Configurar en .env o variable de entorno")
        return False
    
    print(f"🔌 Conectando a BD existente...")
    
    try:
        # Conectar a tu base de datos EXISTENTE
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("✅ Conectado a base de datos existente")
        
        # Verificar que las tablas YA EXISTEN
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('users', 'locations')
            ORDER BY table_name
        """)
        tables = [row['table_name'] for row in cursor.fetchall()]
        
        if 'users' not in tables or 'locations' not in tables:
            print(f"❌ Tablas faltantes. Encontradas: {tables}")
            print("💡 Asegurar que la BD tiene las tablas: users, locations")
            return False
        
        print(f"✅ Tablas verificadas: {tables}")
        
        # Verificar usuarios existentes
        cursor.execute("SELECT COUNT(*) as count FROM users")
        existing_count = cursor.fetchone()['count']
        print(f"📊 Usuarios existentes: {existing_count}")
        
        # Verificar ubicaciones existentes
        cursor.execute("SELECT id, name FROM locations ORDER BY id LIMIT 1")
        location = cursor.fetchone()
        
        if not location:
            print("❌ No hay ubicaciones en la BD")
            print("💡 ¿Crear una ubicación de prueba? (y/n)")
            if input().lower() == 'y':
                cursor.execute("""
                    INSERT INTO locations (name, type, address, is_active, created_at)
                    VALUES ('Local Principal', 'local', 'Dirección de prueba', true, NOW())
                    RETURNING id, name
                """)
                location = cursor.fetchone()
                conn.commit()
                print(f"✅ Ubicación creada: {location['name']}")
            else:
                return False
        else:
            print(f"📍 Usando ubicación: {location['name']} (ID: {location['id']})")
        
        # Setup password hashing
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Usuarios de prueba
        test_users = [
            ("boss@tustockya.com", "boss123", "Carlos", "CEO", "boss"),
            ("admin@tustockya.com", "admin123", "Ana", "Administradora", "administrador"),
            ("vendedor@tustockya.com", "vendedor123", "Juan", "Vendedor", "vendedor"),
            ("vendedor2@tustockya.com", "vendedor123", "María", "Vendedora", "vendedor"),
            ("bodeguero@tustockya.com", "bodeguero123", "Pedro", "Bodeguero", "bodeguero"),
            ("corredor@tustockya.com", "corredor123", "Luis", "Corredor", "corredor")
        ]
        
        created_count = 0
        
        for email, password, first_name, last_name, role in test_users:
            # Verificar si ya existe
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                print(f"⏭️  Usuario {email} ya existe")
                continue
            
            # Hash password
            password_hash = pwd_context.hash(password)
            
            # Crear usuario
            cursor.execute("""
                INSERT INTO users (
                    email, password_hash, first_name, last_name, 
                    role, location_id, is_active, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (email, password_hash, first_name, last_name, role, location['id'], True))
            
            user_id = cursor.fetchone()['id']
            created_count += 1
            print(f"✅ Usuario creado: {email} / {password} ({role}) [ID: {user_id}]")
        
        # Commit cambios
        conn.commit()
        
        # Resumen
        if created_count > 0:
            print(f"\n🎉 {created_count} usuarios creados en BD existente!")
        else:
            print(f"\nℹ️  Todos los usuarios ya existían")
        
        print(f"📍 Ubicación: {location['name']} (ID: {location['id']})")
        print(f"\n📋 Credenciales para testing:")
        
        for email, password, first_name, last_name, role in test_users:
            print(f"   👤 {role.upper():12} | {email:25} | {password}")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error de BD: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)