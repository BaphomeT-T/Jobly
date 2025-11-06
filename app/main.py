from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import psycopg2.extras
from db import get_db_connection, hash_password, verify_password, DDL_SQL

app = FastAPI(title="Jobly Backend API")

# ----------------------------------------------------
# 1. Rutas Estáticas y Servir HTML
# Crea una carpeta 'static' en jobly_backend y pon index.html dentro.
# ----------------------------------------------------

# Monta la carpeta 'static' para servir archivos como CSS o JS.
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Sirve el archivo index.html para la pantalla de inicio."""
    try:
        with open("static/index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>Error 404: Archivo index.html no encontrado.</h1>", status_code=404)

# ----------------------------------------------------
# 2. Funciones de Base de Datos y Inicialización
# ----------------------------------------------------

def run_ddl_on_db():
    """Ejecuta el DDL para crear todas las tablas."""
    conn = get_db_connection()
    if conn is None:
        return {"status": "Error", "message": "No se pudo conectar a la base de datos."}
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_SQL)
            conn.commit()
        return {"status": "OK", "message": "Tablas creadas/verificadas exitosamente."}
    except Exception as e:
        conn.rollback()
        return {"status": "Error", "message": f"Error ejecutando DDL: {e}"}
    finally:
        conn.close()

# Inicialización al arrancar
@app.on_event("startup")
async def startup_event():
    print("Inicializando base de datos...")
    result = run_ddl_on_db()
    print(result['message'])


# ----------------------------------------------------
# 3. Modelos (Pydantic) para Peticiones
# ----------------------------------------------------

class UserRegistration(BaseModel):
    email: str
    password: str
    rol: str # 'Candidato' o 'Empresa'

# ----------------------------------------------------
# 4. Endpoints de Autenticación
# ----------------------------------------------------

@app.post("/api/register/")
async def register_user(data: UserRegistration):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    
    hashed_password = hash_password(data.password)
    
    # 1. Insertar en USUARIO
    user_sql = """
    INSERT INTO USUARIO (Email, Password, Rol)
    VALUES (%s, %s, %s)
    RETURNING ID_Usuario;
    """
    
    try:
        with conn.cursor() as cur:
            # Insertar Usuario
            cur.execute(user_sql, (data.email, hashed_password, data.rol))
            user_id = cur.fetchone()[0]
            
            # 2. Insertar en la tabla de Rol específica
            if data.rol == 'Candidato':
                # Solo se requiere el FK_ID_Usuario para la creación inicial
                candidato_sql = "INSERT INTO CANDIDATO (FK_ID_Usuario, Nombre_Completo) VALUES (%s, %s);"
                cur.execute(candidato_sql, (user_id, data.email)) # Usamos email como nombre temporal
                
            elif data.rol == 'Empresa':
                empresa_sql = "INSERT INTO EMPRESA (FK_ID_Usuario, Nombre_Empresa, RUC) VALUES (%s, %s, %s);"
                # Se necesita más info, pero por ahora usamos valores temporales
                cur.execute(empresa_sql, (user_id, f"Empresa-{user_id}", f"RUC-{user_id}")) 
                
            conn.commit()
            return {"message": f"Usuario {data.rol} registrado exitosamente", "user_id": user_id}

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail="El email ya está registrado.")
    except Exception as e:
        conn.rollback()
        print(f"Error durante el registro: {e}")
        raise HTTPException(status_code=500, detail="Error interno durante el registro.")
    finally:
        conn.close()

# Nota: El endpoint de LOGIN necesitaría JWT o manejo de sesiones, 
# se omite por simplicidad inicial, pero se debe agregar para un proyecto real.