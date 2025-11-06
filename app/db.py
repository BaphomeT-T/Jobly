import psycopg2
import os
from dotenv import load_dotenv
from passlib.context import CryptContext

# Carga las variables del archivo .env
load_dotenv()

# Contexto para hashing de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_connection():
    """Establece y retorna la conexión a la base de datos PostgreSQL.
    Prioriza DATABASE_URL (Railway). Añade sslmode=require si no está presente."""
    # Intentar URL completa (Railway)
    database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
    try:
        if database_url:
            # Asegurar sslmode=require para conexiones remotas
            if "sslmode=" not in database_url:
                if "?" in database_url:
                    database_url = f"{database_url}&sslmode=require"
                else:
                    database_url = f"{database_url}?sslmode=require"
            # psycopg2 acepta la DSN completa
            conn = psycopg2.connect(database_url)
            return conn

        # Fallback a variables separadas (desarrollo/local)
        conn = psycopg2.connect(
            host=os.getenv('PGHOST') or os.getenv('PG_HOST'),
            port=int(os.getenv('PGPORT') or os.getenv('PG_PORT') or 5432),
            user=os.getenv('PGUSER') or os.getenv('PG_USER'),
            password=os.getenv('PGPASSWORD') or os.getenv('PG_PASSWORD'),
            dbname=os.getenv('PGDATABASE') or os.getenv('PG_NAME') or os.getenv('POSTGRES_DB')
        )
        return conn
    except Exception as e:
        print(f"Error conectando a PostgreSQL: {e}")
        return None

def hash_password(password: str) -> str:
    """Hashea una contraseña."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña hasheada."""
    return pwd_context.verify(plain_password, hashed_password)

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
    Nombre_Completo VARCHAR(255) NOT NULL,
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
    RUC VARCHAR(20) UNIQUE NOT NULL,
    Categoria VARCHAR(100),
    Descripcion TEXT
);

-- TABLA ADMINISTRADOR
CREATE TABLE IF NOT EXISTS ADMINISTRADOR (
    ID_Admin SERIAL PRIMARY KEY,
    FK_ID_Usuario INT UNIQUE NOT NULL REFERENCES USUARIO(ID_Usuario),
    Nivel_Acceso VARCHAR(50) NOT NULL DEFAULT 'Basico'
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
    Estado_Proceso VARCHAR(50) NOT NULL CHECK (Estado_Proceso IN ('Recibida','Revision','Entrevista','Oferta','Rechazada')) DEFAULT 'Recibida',
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
"""