import psycopg2
import os
from dotenv import load_dotenv
from passlib.context import CryptContext

# Carga las variables del archivo .env (solo para desarrollo local)
load_dotenv()

# Cambiado a pbkdf2_sha256 para evitar dependencias problemáticas de bcrypt en el entorno
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def get_db_connection():
    """Establece y retorna la conexión a la base de datos PostgreSQL, usando DATABASE_PUBLIC_URL de Railway."""
    
    # CRÍTICO: Railway proporciona DATABASE_PUBLIC_URL para conexiones externas
    # Intentamos primero PUBLIC_URL, luego DATABASE_URL como fallback para desarrollo local
    database_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    
    try:
        if not database_url:
            print("❌ Error: DATABASE_PUBLIC_URL o DATABASE_URL no están definidas. No se puede conectar.")
            print("   Verifica que la base de datos esté linkeada en Railway.")
            return None
        
        # Mostrar información de conexión (sin credenciales sensibles)
        if "railway.app" in database_url:
            print(f"🔄 Intentando conectar a Railway PostgreSQL...")
        else:
            print(f"🔄 Intentando conectar a base de datos local...")
            
        # Asegurar sslmode=require para conexiones remotas si no está presente
        if "railway.app" in database_url and "sslmode=" not in database_url:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=require"
                
        # psycopg2 acepta la DSN (Data Source Name) completa
        conn = psycopg2.connect(database_url)
        print("✅ Conexión a PostgreSQL exitosa")
        return conn

    except psycopg2.OperationalError as e:
        print(f"❌ Error de conexión a PostgreSQL: {e}")
        print("   Posibles causas:")
        print("   1. La base de datos no está linkeada en Railway")
        print("   2. DATABASE_PUBLIC_URL no está configurada correctamente")
        print("   3. La base de datos no está disponible")
        return None
    except Exception as e:
        print(f"❌ Error inesperado conectando a PostgreSQL: {e}")
        return None

def hash_password(password: str) -> str:
    """Hashea una contraseña usando pbkdf2_sha256 por compatibilidad en entorno."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña usando el CryptContext actual.
    Puede lanzar excepciones internas; el llamador puede usar identify_hash_scheme antes."""
    return pwd_context.verify(plain_password, hashed_password)

def identify_hash_scheme(hashed_password: str) -> str | None:
    """Devuelve el nombre del esquema que passlib identifica para este hash, o None si no lo reconoce."""
    try:
        return pwd_context.identify(hashed_password)
    except Exception:
        return None

def is_plain_password(stored_value: str) -> bool:
    """
    Detecta si 'stored_value' parece ser una contraseña en texto plano (no hasheada).
    Reglas simples:
    - si comienza con '$' usualmente es un hash (pbkdf2, bcrypt, etc) -> no es plain
    - si pwd_context.identify lo reconoce -> no es plain
    - en otro caso asumimos que es texto plano (esto permite migrar registros manuales)
    """
    try:
        if stored_value is None:
            return False
        if not isinstance(stored_value, str):
            try:
                stored_value = stored_value.decode("utf-8")
            except Exception:
                return False
        if stored_value.startswith("$"):
            return False
        # si passlib identifica esquema, no es plain
        if identify_hash_scheme(stored_value):
            return False
        # resto: tratamos como plain text (migrable)
        return True
    except Exception:
        return False

def verify_legacy_password(plain_password: str, hashed_password: str) -> bool:
    """
    Intento de verificación para formatos legacy (por ejemplo bcrypt).
    Si bcrypt no está instalado o la verificación falla, devuelve False.
    """
    try:
        if not isinstance(hashed_password, str):
            try:
                hashed_password = hashed_password.decode("utf-8")
            except Exception:
                return False
        # Detectar hashes bcrypt ($2a$, $2b$, $2y$)
        if hashed_password.startswith("$2"):
            try:
                import bcrypt  # import dinámico; puede no existir en el entorno
                return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
            except Exception:
                return False
        return False
    except Exception:
        return False

def init_database():
    """Inicializa las tablas de la base de datos si no existen."""
    conn = get_db_connection()
    
    if not conn:
        print("⚠️  No se pudo inicializar la base de datos - sin conexión")
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(DDL_SQL)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Tablas de base de datos inicializadas correctamente")
        return True
    except Exception as e:
        print(f"❌ Error inicializando tablas: {e}")
        if conn:
            conn.close()
        return False

# Código DDL actualizado para reflejar el MER solicitado
DDL_SQL = """
-- TABLA USUARIO
CREATE TABLE IF NOT EXISTS USUARIO (
    ID_Usuario SERIAL PRIMARY KEY,
    Email VARCHAR(255) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL,
    Rol VARCHAR(50) NOT NULL CHECK (Rol IN ('Candidato', 'Empresa', 'Administrador')),
    Estado_Cuenta VARCHAR(50) NOT NULL DEFAULT 'Activo'
);

-- TABLA CANDIDATO (CV y Foto en BYTEA)
CREATE TABLE IF NOT EXISTS CANDIDATO (
    ID_Candidato SERIAL PRIMARY KEY,
    FK_ID_Usuario INT UNIQUE NOT NULL REFERENCES USUARIO(ID_Usuario),
    CV_PDF_BIN BYTEA,
    Foto_Perfil_BIN BYTEA,
    Nombre_Completo VARCHAR(255),
    Fecha_Nacimiento DATE,
    Genero VARCHAR(50),
    LinkedIn_URL VARCHAR(500),
    GitHub_URL VARCHAR(500),
    Portafolio_URL VARCHAR(500)
);

-- TABLA EMPRESA (Logo/Foto en BYTEA)
CREATE TABLE IF NOT EXISTS EMPRESA (
    ID_Empresa SERIAL PRIMARY KEY,
    FK_ID_Usuario INT UNIQUE NOT NULL REFERENCES USUARIO(ID_Usuario),
    Foto_Logo_BIN BYTEA,
    Nombre_Empresa VARCHAR(255) NOT NULL,
    RUC VARCHAR(20) UNIQUE,
    Categoria VARCHAR(100),
    Descripcion TEXT
);

-- TABLA ADMINISTRADOR
CREATE TABLE IF NOT EXISTS ADMINISTRADOR (
    ID_Admin SERIAL PRIMARY KEY,
    FK_ID_Usuario INT UNIQUE NOT NULL REFERENCES USUARIO(ID_Usuario)
);

-- TABLA VACANTE
CREATE TABLE IF NOT EXISTS VACANTE (
    ID_Vacante SERIAL PRIMARY KEY,
    FK_ID_Empresa INT NOT NULL REFERENCES EMPRESA(ID_Empresa),
    Titulo VARCHAR(255) NOT NULL,
    Descripcion TEXT,
    Salario DECIMAL(10, 2),
    Modalidad VARCHAR(50),
    Estado VARCHAR(50) NOT NULL CHECK (Estado IN ('Borrador','Publicada','Cerrada')) DEFAULT 'Borrador'
);

-- TABLA POSTULACION
CREATE TABLE IF NOT EXISTS POSTULACION (
    ID_Postulacion SERIAL PRIMARY KEY,
    FK_ID_Candidato INT NOT NULL REFERENCES CANDIDATO(ID_Candidato),
    FK_ID_Vacante INT NOT NULL REFERENCES VACANTE(ID_Vacante),
    Fecha_Postulacion TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    Estado_Proceso VARCHAR(50) NOT NULL CHECK (Estado_Proceso IN ('Recibida','Revisión','Entrevista','Oferta','Rechazada')) DEFAULT 'Recibida',
    UNIQUE (FK_ID_Candidato, FK_ID_Vacante)
);

-- TABLA NOTA_INTERNA (Notas relacionadas a una postulacion y rastreables por empresa)
CREATE TABLE IF NOT EXISTS NOTA_INTERNA (
    ID_Nota SERIAL PRIMARY KEY,
    FK_ID_Postulacion INT NOT NULL REFERENCES POSTULACION(ID_Postulacion),
    FK_ID_Empresa INT NOT NULL REFERENCES EMPRESA(ID_Empresa),
    Contenido TEXT NOT NULL,
    Fecha TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- TABLA ENTREVISTA (Relacionado a una postulacion)
CREATE TABLE IF NOT EXISTS ENTREVISTA (
    ID_Entrevista SERIAL PRIMARY KEY,
    FK_ID_Postulacion INT NOT NULL REFERENCES POSTULACION(ID_Postulacion),
    Fecha_Propuesta DATE,
    Hora_Propuesta TIME,
    Enlace_Videollamada TEXT,
    Estado VARCHAR(50) NOT NULL CHECK (Estado IN ('Propuesta','Confirmada','Reprogramada')) DEFAULT 'Propuesta'
);

-- Si la tabla VACANTE ya existe, añadimos la columna Fecha_Creacion si falta.
ALTER TABLE VACANTE
    ADD COLUMN IF NOT EXISTS Fecha_Creacion TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP;
"""
