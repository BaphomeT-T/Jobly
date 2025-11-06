import os
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
# **********************************************
# IMPORTACIÓN CORREGIDA: Usamos "." para la importación relativa
from .db import get_db_connection, hash_password, verify_password, DDL_SQL 
# **********************************************

app = FastAPI(title="Jobly Backend API")

# ----------------------------------------------------
# 1. Rutas Estáticas y Servir HTML
# ----------------------------------------------------

# Monta la carpeta 'static' para servir archivos como CSS o JS.
# Usamos os.path.join para asegurar compatibilidad de rutas
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Sirve el archivo index.html para la pantalla de inicio."""
    try:
        # Usamos 'utf-8' explícitamente y la ruta relativa corregida
        with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>Error 404: Archivo index.html no encontrado.</h1>", status_code=404)

# --- Nueva ruta para servir el formulario de registro de candidato
@app.get("/register", response_class=HTMLResponse)
async def serve_register():
    """Sirve el archivo register.html para el registro de candidatos."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "static", "register.html"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>Error 404: Registro no encontrado.</h1>", status_code=404)

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

# --- Nuevo endpoint: registro de candidato via multipart/form-data ---
@app.post("/api/register_candidate/")
async def register_candidate(
    email: str = Form(...),
    password: str = Form(...),
    nombre_completo: str = Form(...),
    cv: UploadFile = File(None),
    foto: UploadFile = File(None)
):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")

    # leer archivos si existen
    cv_bytes = await cv.read() if cv else None
    foto_bytes = await foto.read() if foto else None

    hashed_password = hash_password(password)

    user_sql = """
    INSERT INTO USUARIO (Email, Password, Rol)
    VALUES (%s, %s, %s)
    RETURNING ID_Usuario;
    """
    candidato_sql = """
    INSERT INTO CANDIDATO (FK_ID_Usuario, CV_PDF_BIN, Foto_Perfil_BIN, Nombre_Completo)
    VALUES (%s, %s, %s, %s);
    """
    try:
        with conn.cursor() as cur:
            cur.execute(user_sql, (email, hashed_password, 'Candidato'))
            user_id = cur.fetchone()[0]
            cur.execute(candidato_sql, (
                user_id,
                psycopg2.Binary(cv_bytes) if cv_bytes else None,
                psycopg2.Binary(foto_bytes) if foto_bytes else None,
                nombre_completo
            ))
            conn.commit()
            return {"message": "Candidato registrado", "user_id": user_id}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail="El email ya está registrado.")
    except Exception as e:
        conn.rollback()
        print("Error register_candidate:", e)
        raise HTTPException(status_code=500, detail="Error interno durante el registro.")
    finally:
        conn.close()

@app.get("/api/download_last_cv")
async def download_last_cv():
    """
    Devuelve el último CV (CV_PDF_BIN) almacenado en CANDIDATO como attachment PDF.
    Busca el registro más reciente con CV no nulo.
    """
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT CV_PDF_BIN, Nombre_Completo
                FROM CANDIDATO
                WHERE CV_PDF_BIN IS NOT NULL
                ORDER BY ID_Candidato DESC
                LIMIT 1;
            """)
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(status_code=404, detail="No hay CVs disponibles")
            cv_bytes = row[0]
            nombre = row[1] or "usuario"
            filename = f'cv_{nombre}.pdf'.replace(' ', '_')
            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
            return Response(content=cv_bytes.tobytes() if hasattr(cv_bytes, "tobytes") else cv_bytes,
                            media_type="application/pdf",
                            headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        print("Error descargando último CV:", e)
        raise HTTPException(status_code=500, detail="Error interno al obtener el CV")
    finally:
        conn.close()