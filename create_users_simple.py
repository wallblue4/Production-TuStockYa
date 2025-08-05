#!/usr/bin/env python3
"""
Script simple para crear usuarios - NO depende de archivos de app/
"""
import os

def main():
    print("🚀 TuStockYa - Creando usuarios de prueba...")
    
    try:
        # Imports básicos
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from passlib.context import CryptContext
        from dotenv import load_dotenv
        
        print("✅ Dependencias cargadas")
        
        # Cargar variables de entorno
        load_dotenv()
        
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            print("❌ ERROR: Falta DATABASE_URL en archivo .env")
            print("💡 Crear archivo .env con tu configuración de PostgreSQL")
            print("💡 Ejemplo: DATABASE_URL=postgresql://usuario:password@localhost:5432/database")
            return False
        
        print(f"🔌 Conectando a: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'database'}...")
        
        # Conectar a PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("✅ Conectado a PostgreSQL exitosamente")
        
        # Verificar tablas
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('users', 'locations')
            ORDER BY table_name
        """)
        tables = [row['table_name'] for row in cursor.fetchall()]
        print(f"📋 Tablas encontradas: {tables}")
        
        if 'users' not in tables:
            print("❌ Tabla 'users' no existe")
            return False
        if 'locations' not in tables:
            print("❌ Tabla 'locations' no existe")
            return False
        
        # Configurar hash de passwords
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Verificar/crear ubicación
        cursor.execute("SELECT id, name FROM locations ORDER BY id LIMIT 1")
        location = cursor.fetchone()
        
        if not location:
            print("📍 Creando ubicación de prueba...")
            cursor.execute("""
                INSERT INTO locations (name, type, address, is_active, created_at)
                VALUES ('Local Principal', 'local', 'Calle Principal 123', true, NOW())
                RETURNING id, name
            """)
            location = cursor.fetchone()
            conn.commit()
            print(f"✅ Ubicación creada: {location['name']}")
        else:
            print(f"📍 Usando ubicación existente: {location['name']} (ID: {location['id']})")
        
        # Usuarios de prueba
        usuarios = [
            ("boss@tustockya.com", "boss123", "Carlos", "Jefe", "boss"),
            ("admin@tustockya.com", "admin123", "Ana", "Administradora", "administrador"),
            ("vendedor@tustockya.com", "vendedor123", "Juan", "Vendedor", "vendedor"),
            ("vendedor2@tustockya.com", "vendedor123", "María", "Vendedora", "vendedor"),
            ("bodeguero@tustockya.com", "bodeguero123", "Pedro", "Bodeguero", "bodeguero"),
            ("corredor@tustockya.com", "corredor123", "Luis", "Corredor", "corredor")
        ]
        
        creados = 0
        
        for email, password, first_name, last_name, role in usuarios:
            # Verificar si ya existe
            cursor.execute("SELECT id, email FROM users WHERE email = %s", (email,))
            existing = cursor.fetchone()
            
            if existing:
                print(f"⏭️  Usuario {email} ya existe (ID: {existing['id']})")
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
            creados += 1
            
            print(f"✅ Usuario creado: {email} / {password} ({role}) [ID: {user_id}]")
        
        # Commit todos los cambios
        conn.commit()
        
        # Resumen final
        if creados > 0:
            print(f"\n🎉 ¡{creados} usuarios creados exitosamente!")
        else:
            print(f"\nℹ️  Todos los usuarios ya existían")
            
        print(f"📍 Ubicación asignada: {location['name']} (ID: {location['id']})")
        print(f"\n📋 Credenciales para testing:")
        
        for email, password, first_name, last_name, role in usuarios:
            print(f"   👤 {role.upper():12} | {email:25} | {password}")
        
        print(f"\n💡 Próximo paso: Ejecutar la aplicación con:")
        print(f"   python -m app.main")
        
        return True
        
    except ImportError as e:
        print(f"❌ Error importando librerías: {e}")
        print(f"💡 Instalar dependencias:")
        print(f"   pip install psycopg2-binary python-dotenv passlib[bcrypt]")
        return False
        
    except psycopg2.OperationalError as e:
        print(f"❌ Error conectando a base de datos: {e}")
        print(f"💡 Verificar:")
        print(f"   1. PostgreSQL está ejecutándose")
        print(f"   2. Credenciales en .env son correctas") 
        print(f"   3. Base de datos existe")
        return False
        
    except psycopg2.Error as e:
        print(f"❌ Error de PostgreSQL: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        if 'conn' in locals():
            conn.rollback()
        return False
        
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Conexión a base de datos cerrada")

if __name__ == "__main__":
    success = main()
    if not success:
        print(f"\n❌ Script falló. Revisar errores arriba.")
        exit(1)
    else:
        print(f"\n✅ Script completado exitosamente")
