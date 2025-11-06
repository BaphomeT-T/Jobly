import psycopg2
import os
from dotenv import load_dotenv
from passlib.context import CryptContext

# Carga las variables del archivo .env
load_dotenv()

# Contexto para hashing de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_connection():
    """Establece y retorna la conexión a la base de datos PostgreSQL de Railway."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('PG_HOST'),
            port=os.getenv('PG_PORT'),
            user=os.getenv('PG_USER'),
            password=os.getenv('PG_PASSWORD'),
            dbname=os.getenv('PG_NAME')
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

# Código DDL para inicializar las tablas (Se ejecuta una sola vez en Railway)
DDL_SQL = """
-- TABLA USUARIO
CREATE TABLE IF NOT EXISTS USUARIO (
    ID_Usuario SERIAL PRIMARY KEY,
    Email VARCHAR(255) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL,
    Rol VARCHAR(50) NOT NULL CHECK (Rol IN ('Candidato', 'Empresa', 'Administrador')),
    Estado_Cuenta VARCHAR(50) NOT NULL DEFAULT 'Activo'
);

-- TABLA CANDIDATO (Contenido binario CV y Foto en BYTEA)
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

-- TABLA EMPRESA (Contenido binario Logo/Foto en BYTEA)
CREATE TABLE IF NOT EXISTS EMPRESA (
    ID_Empresa SERIAL PRIMARY KEY,
    FK_ID_Usuario INT UNIQUE NOT NULL REFERENCES USUARIO(ID_Usuario),
    Foto_Logo_BIN BYTEA,
    Nombre_Empresa VARCHAR(255) NOT NULL,
    RUC VARCHAR(20) UNIQUE NOT NULL,
    Categoria VARCHAR(100),
    Descripcion TEXT
);

-- TABLA VACANTE
CREATE TABLE IF NOT EXISTS VACANTE (
    ID_Vacante SERIAL PRIMARY KEY,
    FK_ID_Empresa INT NOT NULL REFERENCES EMPRESA(ID_Empresa),
    Titulo VARCHAR(255) NOT NULL,
    Descripcion TEXT,
    Salario DECIMAL(10, 2),
    Modalidad VARCHAR(50),
    Estado VARCHAR(50) NOT NULL
);

-- TABLA POSTULACION
CREATE TABLE IF NOT EXISTS POSTULACION (
    ID_Postulacion SERIAL PRIMARY KEY,
    FK_ID_Candidato INT NOT NULL REFERENCES CANDIDATO(ID_Candidato),
    FK_ID_Vacante INT NOT NULL REFERENCES VACANTE(ID_Vacante),
    Fecha_Postulacion TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    Estado_Proceso VARCHAR(50) NOT NULL,
    UNIQUE (FK_ID_Candidato, FK_ID_Vacante)
);
"""