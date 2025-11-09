import os
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
# **********************************************
# IMPORTACIÓN CORREGIDA: Usamos "." para la importación relativa
from .db import get_db_connection, hash_password, verify_password, DDL_SQL 
# **********************************************

app = FastAPI(title="Jobly Backend API")

# Configuración de CORS para permitir acceso desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# 1. Rutas Estáticas y Servir HTML
# ----------------------------------------------------

# Monta la carpeta 'static' para servir archivos como CSS o JS.
# Usamos os.path.join para asegurar compatibilidad de rutas
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

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

# --- Rutas para flujo de registro de empresa (pasos) ---
def _serve_static_html(filename: str, not_found_label: str):
    try:
        with open(os.path.join(os.path.dirname(__file__), "static", filename), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(f"<h1>Error 404: {not_found_label} no encontrado.</h1>", status_code=404)

@app.get("/register/employer/step1", response_class=HTMLResponse)
async def employer_step1():
    return _serve_static_html("employer-step1.html", "Paso 1 empresa")

@app.get("/register/employer/step2", response_class=HTMLResponse)
async def employer_step2():
    return _serve_static_html("employer-step2.html", "Paso 2 empresa")

@app.get("/register/employer/step3", response_class=HTMLResponse)
async def employer_step3():
    return _serve_static_html("employer-step3.html", "Paso 3 empresa")

# Ruta para registro de candidato (empleado) paso 1
@app.get("/register/empleado/step1", response_class=HTMLResponse)
async def empleado_step1():
    return _serve_static_html("empleado-step1.html", "Paso 1 candidato")

@app.get("/register/empleado/step2", response_class=HTMLResponse)
async def empleado_step2():
    return _serve_static_html("empleado-step2.html", "Paso 2 candidato")

@app.get("/register/empleado/step3", response_class=HTMLResponse)
async def empleado_step3():
    return _serve_static_html("empleado-step3.html", "Paso 3 candidato")

# Ruta para home de empleados (después de login exitoso)
@app.get("/home-empleados", response_class=HTMLResponse)
async def home_empleados():
    return _serve_static_html("home-empleados.html", "Home Empleados")

# Ruta para login
@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    return _serve_static_html("login.html", "Login")

# Ruta de debug para verificar archivos estáticos
@app.get("/debug/static-files")
async def debug_static_files():
    """Endpoint para verificar que los archivos estáticos existen"""
    static_path = os.path.join(os.path.dirname(__file__), "static")
    files = []
    for root, dirs, filenames in os.walk(static_path):
        for filename in filenames:
            rel_path = os.path.relpath(os.path.join(root, filename), static_path)
            files.append(rel_path)
    return {
        "static_directory": static_path,
        "exists": os.path.exists(static_path),
        "files": sorted(files)
    }

# Ruta de debug para verificar todas las rutas registradas
@app.get("/debug/routes")
async def debug_routes():
    """Endpoint para verificar todas las rutas registradas en la aplicación"""
    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append({
                "path": route.path,
                "name": route.name if hasattr(route, "name") else None,
                "methods": list(route.methods) if hasattr(route, "methods") else []
            })
    return {"routes": routes}

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

# (opcional) versión con cookie sencilla (no JWT) — puedes mantener como está si prefieres usar solo localStorage
from fastapi import Response

# --- Endpoint para Login ---
@app.post("/api/login/")
async def login_user(email: str = Form(...), password: str = Form(...)):
    """
    Valida las credenciales y devuelve datos mínimos + ruta de redirección.
    """
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT ID_Usuario, Email, Password, Rol
                FROM USUARIO
                WHERE Email = %s
            """, (email,))
            user = cur.fetchone()
            
            if not user:
                raise HTTPException(status_code=401, detail="Credenciales incorrectas")
            
            # OJO: DictCursor devuelve claves por nombre de columna; accedemos en minúsculas
            if not verify_password(password, user["password"]):
                raise HTTPException(status_code=401, detail="Credenciales incorrectas")
            
            rol = user["rol"]
            redirect = "/home-empresa" if rol == "Empresa" else "/home-empleados"

            return {
                "message": "Inicio de sesión exitoso",
                "user_id": user["id_usuario"],
                "email": user["email"],
                "rol": rol,
                "redirect": redirect
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error durante el login: {e}")
        raise HTTPException(status_code=500, detail="Error interno durante el login.")
    finally:
        conn.close()


# --- Endpoint para registro de empresa multipart (pasos 1-3 flujo) ---
@app.post("/api/register_employer/")
async def register_employer(
    email: str = Form(...),
    password: str = Form(...),
    nombre_empresa: str = Form(...),
    ruc: str = Form(""),
    categoria: str = Form(""),
    descripcion: str = Form(""),
    logo: UploadFile | None = File(None)
):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")

    logo_bytes = await logo.read() if logo else None

    hashed_password = hash_password(password)

    user_sql = """
    INSERT INTO USUARIO (Email, Password, Rol)
    VALUES (%s, %s, %s)
    RETURNING ID_Usuario;
    """
    empresa_sql = """
    INSERT INTO EMPRESA (FK_ID_Usuario, Foto_Logo_BIN, Nombre_Empresa, RUC, Categoria, Descripcion)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING ID_Empresa;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(user_sql, (email, hashed_password, 'Empresa'))
            user_id = cur.fetchone()[0]
            cur.execute(empresa_sql, (user_id, psycopg2.Binary(logo_bytes) if logo_bytes else None, nombre_empresa, ruc or None, categoria or None, descripcion or None))
            empresa_id = cur.fetchone()[0]
            conn.commit()
            return {"message": "Empresa registrada exitosamente", "user_id": user_id, "empresa_id": empresa_id}
    except psycopg2.errors.UniqueViolation as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="El email o RUC ya está registrado.")
    except Exception as e:
        conn.rollback()
        print("Error register_employer:", e)
        raise HTTPException(status_code=500, detail="Error interno durante el registro de empresa.")
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
        
@app.get("/home-vacantes", response_class=HTMLResponse)
async def home_vacantes():
    return _serve_static_html("home-vacantes.html", "Home Vacantes")

@app.get("/home-empresa", response_class=HTMLResponse)
async def home_empresa():
    return _serve_static_html("home-empresa.html", "Home Empresa")
