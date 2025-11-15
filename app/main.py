import os
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import re
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# **********************************************
# IMPORTACIÓN CORREGIDA: Usamos "." para la importación relativa
from .db import get_db_connection, hash_password, verify_password, identify_hash_scheme, verify_legacy_password, is_plain_password, DDL_SQL 
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

# Sesiones firmadas (HttpOnly cookie)
session_secret = os.getenv("SESSION_SECRET", "dev-session-secret-change")
logger.info(f"Configuring SessionMiddleware with secret: {session_secret[:10]}...")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="lax"
)

logger.info("✅ FastAPI app configured successfully")
logger.info(f"🚀 Starting Jobly API - PORT: {os.getenv('PORT', 'not set')}")
logger.info(f"📦 Database URL configured: {'Yes' if os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL') else 'No'}")

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
    logger.info("Serving index.html at root /")
    try:
        # Usamos 'utf-8' explícitamente y la ruta relativa corregida
        with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("index.html not found")
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

# Nuevo home para postulantes (candidatos)
@app.get("/home-postulantes", response_class=HTMLResponse)
async def home_postulantes():
    return _serve_static_html("home-postulantes.html", "Home Postulantes")

# Ruta para login
@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    return _serve_static_html("login.html", "Login")

# Ruta para página de éxito - vacante publicada
@app.get("/vacante-publicada", response_class=HTMLResponse)
async def vacante_publicada():
    return _serve_static_html("Vacante-publicada.html", "Vacante Publicada")

# Ruta para crear/realizar vacante (formulario)
@app.get("/realizar-vacante", response_class=HTMLResponse)
async def realizar_vacante():
    return _serve_static_html("realizar-vacante.html", "Crear Vacante")

# Ruta para ver vacantes (empresa)
@app.get("/ver-vacantes", response_class=HTMLResponse)
async def ver_vacantes():
    return _serve_static_html("ver-vacantes.html", "Ver Vacantes")

# Ruta para editar vacante (empresa)
@app.get("/editar-vacante", response_class=HTMLResponse)
async def editar_vacante():
    return _serve_static_html("editar-vacante.html", "Editar Vacante")


@app.get("/editar-perfil", response_class=HTMLResponse)
async def editar_perfil():
    """Sirve la página de editar perfil creada desde diseño Figma."""
    return _serve_static_html("editar-perfil.html", "Editar Perfil")

# API: Obtener vacantes de una empresa por email
@app.get("/api/vacantes/empresa")
async def get_vacantes_empresa(request: Request, email: str | None = None):
    """
    Obtiene todas las vacantes de una empresa identificada por el email del usuario.
    Incluye el conteo de postulaciones por vacante.
    """
    # Priorizar email desde la sesión; fallback temporal al query param
    session_user = request.session.get("user") if hasattr(request, "session") else None
    session_email = (session_user or {}).get("email") if isinstance(session_user, dict) else None
    effective_email = session_email or email

    if not effective_email:
        raise HTTPException(status_code=401, detail="No autenticado")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Obtener ID_Empresa desde el email
            cur.execute("""
                SELECT e.ID_Empresa
                FROM EMPRESA e
                JOIN USUARIO u ON e.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
            """, (effective_email,))
            empresa = cur.fetchone()
            
            if not empresa:
                return {"vacantes": []}
            
            id_empresa = empresa["id_empresa"]
            
            # Obtener vacantes con conteo de postulaciones
            cur.execute("""
                SELECT 
                    v.ID_Vacante,
                    v.Titulo,
                    v.Descripcion,
                    v.Salario,
                    v.Modalidad,
                    v.Estado,
                    v.Fecha_Creacion,
                    COUNT(p.ID_Postulacion) as num_postulaciones
                FROM VACANTE v
                LEFT JOIN POSTULACION p ON v.ID_Vacante = p.FK_ID_Vacante
                WHERE v.FK_ID_Empresa = %s
                GROUP BY v.ID_Vacante
                ORDER BY v.Fecha_Creacion DESC;
            """, (id_empresa,))
            
            vacantes = cur.fetchall()
            
            # Convertir a formato JSON serializable
            result = []
            for v in vacantes:
                result.append({
                    "id_vacante": v["id_vacante"],
                    "titulo": v["titulo"],
                    "descripcion": v["descripcion"],
                    "salario": float(v["salario"]) if v["salario"] else None,
                    "modalidad": v["modalidad"],
                    "estado": v["estado"],
                    "fecha_creacion": v["fecha_creacion"].isoformat() if v["fecha_creacion"] else None,
                    "num_postulaciones": v["num_postulaciones"]
                })
            
            return {"vacantes": result}
            
    except Exception as e:
        print(f"Error obteniendo vacantes: {e}")
        raise HTTPException(status_code=500, detail="Error interno obteniendo vacantes")
    finally:
        conn.close()

@app.get("/api/me")
async def api_me(request: Request):
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    # Keep legacy simple object response for existing clients
    return user

@app.post("/api/logout")
async def api_logout(request: Request):
    try:
        if hasattr(request, "session"):
            request.session.clear()
    except Exception as e:
        print("Error limpiando sesión:", e)
    return {"message": "Sesión cerrada"}

# Ruta para actividades (empresa)
@app.get("/actividades", response_class=HTMLResponse)
async def actividades():
    return _serve_static_html("actividades.html", "Actividades")

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
async def login_user(request: Request, email: str = Form(...), password: str = Form(...)):
    """
    Valida las credenciales y maneja migración de hashes legacy o texto plano.
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
            
            stored_hash = user["password"]
            verified = False

            # 1) Si passlib identifica el esquema -> verificar normalmente
            scheme = identify_hash_scheme(stored_hash)
            if scheme:
                try:
                    verified = verify_password(password, stored_hash)
                except Exception:
                    verified = False
            else:
                # 2) Si el valor en BD parece texto plano, comparar directamente y migrar
                if is_plain_password(stored_hash):
                    if password == (stored_hash or ""):
                        verified = True
                        try:
                            new_hash = hash_password(password)
                            cur.execute("UPDATE USUARIO SET Password = %s WHERE ID_Usuario = %s", (new_hash, user["id_usuario"]))
                            conn.commit()
                            print(f"Info: contraseña en texto plano migrada a hash para user_id={user['id_usuario']}")
                        except Exception as e:
                            conn.rollback()
                            print("Warning: no se pudo actualizar hash al migrar desde plain:", e)
                    else:
                        verified = False
                else:
                    # 3) Intentar legacy (bcrypt)
                    if verify_legacy_password(password, stored_hash):
                        verified = True
                        # migrar a esquema actual
                        try:
                            new_hash = hash_password(password)
                            cur.execute("UPDATE USUARIO SET Password = %s WHERE ID_Usuario = %s", (new_hash, user["id_usuario"]))
                            conn.commit()
                            print(f"Info: contraseña legacy migrada a nuevo esquema para user_id={user['id_usuario']}")
                        except Exception as e:
                            conn.rollback()
                            print("Warning: no se pudo actualizar hash al migrar legacy:", e)
                    else:
                        verified = False

            if not verified:
                raise HTTPException(status_code=401, detail="Credenciales incorrectas")
            
            rol = user["rol"]
            # Redirigir según rol: Empresa -> /home-empresa, Candidato -> /home-postulantes
            redirect = "/home-empresa" if rol == "Empresa" else "/home-postulantes"

            # Guardar la información mínima en sesión (cookie firmada)
            try:
                request.session["user"] = {
                    "id_usuario": int(user["id_usuario"]),
                    "email": user["email"],
                    "rol": rol
                }
            except Exception as e:
                print("No se pudo almacenar sesión:", e)

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
        

# --- Crear Vacante ---
class VacanteCreate(BaseModel):
    titulo: str
    descripcion: str | None = None
    salario: float | None = None
    modalidad: str
    # Para identificar a qué empresa pertenece la vacante:
    empresa_email: str  # email del USUARIO dueño de la EMPRESA

class VacanteUpdate(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    salario: float | None = None
    modalidad: str | None = None
    estado: str | None = None  # Borrador, Publicada, Cerrada

@app.post("/api/vacantes/")
async def crear_vacante(data: VacanteCreate):
    """
    Crea una vacante para la empresa asociada al email indicado.
    Busca el ID_Empresa vía USUARIO.Email -> EMPRESA.FK_ID_Usuario
    """
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")

    try:
        with conn.cursor() as cur:
            # 1) Obtener ID_Empresa desde el email del usuario
            cur.execute("""
                SELECT e.ID_Empresa
                FROM EMPRESA e
                JOIN USUARIO u ON e.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
            """, (data.empresa_email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontró una empresa asociada a ese email")
            id_empresa = row[0]

            # 2) Insertar la VACANTE
            cur.execute("""
                INSERT INTO VACANTE (FK_ID_Empresa, Titulo, Descripcion, Salario, Modalidad, Estado)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING ID_Vacante;
            """, (id_empresa, data.titulo, data.descripcion, data.salario, data.modalidad, 'Publicada'))
            id_vacante = cur.fetchone()[0]
            conn.commit()

            return {"message": "Vacante creada", "id_vacante": id_vacante}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        print("Error crear_vacante:", e)
        raise HTTPException(status_code=500, detail="Error interno creando la vacante")
    finally:
        conn.close()


# -----------------------------
# Candidato: Perfil (GET/PUT)
# -----------------------------
class CandidateProfileUpdate(BaseModel):
    nombre_completo: str | None = None
    fecha_nacimiento: str | None = None  # ISO date 'YYYY-MM-DD'
    genero: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portafolio_url: str | None = None


@app.get("/api/candidato/perfil")
async def get_candidato_perfil(request: Request):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")

    email = session_user.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.ID_Usuario, u.Email, u.Rol, u.Estado_Cuenta,
                       c.ID_Candidato, c.Nombre_Completo, c.Fecha_Nacimiento, c.Genero,
                       c.LinkedIn_URL, c.GitHub_URL, c.Portafolio_URL,
                       c.Foto_Perfil_BIN, c.CV_PDF_BIN
                FROM USUARIO u
                LEFT JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            if row["rol"] != "Candidato":
                raise HTTPException(status_code=403, detail="Solo candidatos tienen perfil editable aquí")

            if row["id_candidato"] is None:
                # Crear registro de candidato si no existe aún
                cur.execute(
                    """
                    INSERT INTO CANDIDATO (FK_ID_Usuario, Nombre_Completo)
                    VALUES (%s, %s)
                    RETURNING ID_Candidato
                    """,
                    (row["id_usuario"], row["email"]),
                )
                created = cur.fetchone()
                conn.commit()
                row["id_candidato"] = created["id_candidato"] if isinstance(created, dict) else created[0]

            account = {
                "id_usuario": row["id_usuario"],
                "email": row["email"],
                "rol": row["rol"],
                "estado_cuenta": row["estado_cuenta"],
            }
            profile = {
                "id_candidato": row["id_candidato"],
                "nombre_completo": row["nombre_completo"],
                "fecha_nacimiento": row["fecha_nacimiento"].isoformat() if row["fecha_nacimiento"] else None,
                "genero": row["genero"],
                "linkedin_url": row["linkedin_url"],
                "github_url": row["github_url"],
                "portafolio_url": row["portafolio_url"],
                "has_avatar": bool(row.get("foto_perfil_bin")),
                "has_cv": bool(row.get("cv_pdf_bin")),
            }
            return {"account": account, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error get_candidato_perfil: {e}")
        raise HTTPException(status_code=500, detail="Error interno obteniendo perfil")
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ------------------------------------------
# Candidato: Subida y descarga de Avatar
# ------------------------------------------
@app.post("/api/candidato/avatar")
async def upload_candidato_avatar(request: Request, file: UploadFile = File(...)):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")
    email = session_user.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo requerido")
    if not (file.content_type or "").startswith("image"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")

    data_bytes = await file.read()
    if not data_bytes:
        raise HTTPException(status_code=400, detail="Imagen vacía")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.ID_Usuario, u.Rol, c.ID_Candidato
                FROM USUARIO u
                LEFT JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            if row["rol"] != "Candidato":
                raise HTTPException(status_code=403, detail="Solo candidatos pueden subir avatar")
            if row["id_candidato"] is None:
                cur.execute("INSERT INTO CANDIDATO (FK_ID_Usuario) VALUES (%s) RETURNING ID_Candidato;", (row["id_usuario"],))
                newc = cur.fetchone()
                id_candidato = newc["id_candidato"] if isinstance(newc, dict) else newc[0]
            else:
                id_candidato = row["id_candidato"]

            cur.execute(
                "UPDATE CANDIDATO SET Foto_Perfil_BIN = %s WHERE ID_Candidato = %s RETURNING ID_Candidato;",
                (psycopg2.Binary(data_bytes), id_candidato),
            )
            conn.commit()
            return {"message": "Avatar actualizado", "id_candidato": id_candidato}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error upload avatar: {e}")
        raise HTTPException(status_code=500, detail="Error interno subiendo avatar")
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.get("/api/candidato/avatar")
async def get_candidato_avatar(request: Request):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")
    email = session_user.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.Foto_Perfil_BIN
                FROM USUARIO u
                JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s AND c.Foto_Perfil_BIN IS NOT NULL
                LIMIT 1;
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(status_code=404, detail="Sin avatar")
            img_bytes = row[0]
            return Response(content=img_bytes.tobytes() if hasattr(img_bytes, "tobytes") else img_bytes, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error get avatar: {e}")
        raise HTTPException(status_code=500, detail="Error interno obteniendo avatar")
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ------------------------------------------
# Candidato: Subida y descarga de CV propio
# ------------------------------------------
@app.post("/api/candidato/cv")
async def upload_candidato_cv(request: Request, file: UploadFile = File(...)):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")
    email = session_user.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo requerido")
    if (file.content_type or "") != "application/pdf":
        raise HTTPException(status_code=400, detail="El CV debe ser PDF")
    data_bytes = await file.read()
    if not data_bytes:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.ID_Usuario, u.Rol, c.ID_Candidato
                FROM USUARIO u
                LEFT JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            if row["rol"] != "Candidato":
                raise HTTPException(status_code=403, detail="Solo candidatos pueden subir CV")
            if row["id_candidato"] is None:
                cur.execute("INSERT INTO CANDIDATO (FK_ID_Usuario) VALUES (%s) RETURNING ID_Candidato;", (row["id_usuario"],))
                newc = cur.fetchone()
                id_candidato = newc["id_candidato"] if isinstance(newc, dict) else newc[0]
            else:
                id_candidato = row["id_candidato"]

            cur.execute(
                "UPDATE CANDIDATO SET CV_PDF_BIN = %s WHERE ID_Candidato = %s RETURNING ID_Candidato;",
                (psycopg2.Binary(data_bytes), id_candidato),
            )
            conn.commit()
            return {"message": "CV actualizado", "id_candidato": id_candidato}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error upload cv: {e}")
        raise HTTPException(status_code=500, detail="Error interno subiendo CV")
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.get("/api/candidato/cv")
async def get_candidato_cv(request: Request):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")
    email = session_user.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.CV_PDF_BIN, c.Nombre_Completo
                FROM USUARIO u
                JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s AND c.CV_PDF_BIN IS NOT NULL
                LIMIT 1;
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(status_code=404, detail="Sin CV")
            cv_bytes, nombre = row[0], row[1] or "candidato"
            filename = f"cv_{nombre}.pdf".replace(" ", "_")
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
            return Response(content=cv_bytes.tobytes() if hasattr(cv_bytes, "tobytes") else cv_bytes, media_type="application/pdf", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error get cv: {e}")
        raise HTTPException(status_code=500, detail="Error interno obteniendo CV")
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.put("/api/candidato/perfil")
async def update_candidato_perfil(data: CandidateProfileUpdate, request: Request):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")

    email = session_user.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Ensure candidate row exists
            cur.execute(
                """
                SELECT u.ID_Usuario, u.Rol, c.ID_Candidato
                FROM USUARIO u
                LEFT JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            if row["rol"] != "Candidato":
                raise HTTPException(status_code=403, detail="Solo candidatos pueden editar este perfil")

            if row["id_candidato"] is None:
                cur.execute(
                    "INSERT INTO CANDIDATO (FK_ID_Usuario) VALUES (%s) RETURNING ID_Candidato;",
                    (row["id_usuario"],),
                )
                newc = cur.fetchone()
                id_candidato = newc["id_candidato"] if isinstance(newc, dict) else newc[0]
            else:
                id_candidato = row["id_candidato"]

            fields = []
            params = []
            if data.nombre_completo is not None:
                fields.append("Nombre_Completo = %s")
                params.append(data.nombre_completo)
            if data.fecha_nacimiento is not None:
                fields.append("Fecha_Nacimiento = %s")
                params.append(data.fecha_nacimiento)
            if data.genero is not None:
                fields.append("Genero = %s")
                params.append(data.genero)
            if data.linkedin_url is not None:
                fields.append("LinkedIn_URL = %s")
                params.append(data.linkedin_url)
            if data.github_url is not None:
                fields.append("GitHub_URL = %s")
                params.append(data.github_url)
            if data.portafolio_url is not None:
                fields.append("Portafolio_URL = %s")
                params.append(data.portafolio_url)

            if not fields:
                raise HTTPException(status_code=400, detail="No hay campos para actualizar")

            params.append(id_candidato)
            cur.execute(
                f"UPDATE CANDIDATO SET {', '.join(fields)} WHERE ID_Candidato = %s RETURNING ID_Candidato;",
                params,
            )
            conn.commit()
            return {"message": "Perfil actualizado", "id_candidato": id_candidato}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error update_candidato_perfil: {e}")
        raise HTTPException(status_code=500, detail="Error interno actualizando perfil")
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.get("/api/vacantes/{id_vacante}")
async def get_vacante_by_id(id_vacante: int, request: Request):
    """
    Obtiene los datos de una vacante específica por su ID.
    Verifica que la vacante pertenezca a la empresa del usuario autenticado.
    """
    # Get user from session
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")
    
    session_email = session_user.get("email")
    if not session_email:
        raise HTTPException(status_code=401, detail="No autenticado")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get empresa ID from session email
            cur.execute("""
                SELECT e.ID_Empresa
                FROM EMPRESA e
                JOIN USUARIO u ON e.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
            """, (session_email,))
            empresa = cur.fetchone()
            
            if not empresa:
                raise HTTPException(status_code=404, detail="Empresa no encontrada")
            
            id_empresa = empresa["id_empresa"]
            
            # Get vacancy data and verify ownership
            cur.execute("""
                SELECT 
                    ID_Vacante,
                    Titulo,
                    Descripcion,
                    Salario,
                    Modalidad,
                    Estado,
                    Fecha_Creacion
                FROM VACANTE
                WHERE ID_Vacante = %s AND FK_ID_Empresa = %s
                LIMIT 1;
            """, (id_vacante, id_empresa))
            
            vacante = cur.fetchone()
            
            if not vacante:
                raise HTTPException(status_code=404, detail="Vacante no encontrada o no autorizada")
            
            return {
                "id_vacante": vacante["id_vacante"],
                "titulo": vacante["titulo"],
                "descripcion": vacante["descripcion"],
                "salario": float(vacante["salario"]) if vacante["salario"] else None,
                "modalidad": vacante["modalidad"],
                "estado": vacante["estado"],
                "fecha_creacion": vacante["fecha_creacion"].isoformat() if vacante["fecha_creacion"] else None
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error get_vacante_by_id: {e}")
        raise HTTPException(status_code=500, detail="Error interno obteniendo la vacante")
    finally:
        conn.close()


@app.put("/api/vacantes/{id_vacante}")
async def update_vacante(id_vacante: int, data: VacanteUpdate, request: Request):
    """
    Actualiza una vacante existente.
    Verifica que la vacante pertenezca a la empresa del usuario autenticado.
    """
    # Get user from session
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or not isinstance(session_user, dict):
        raise HTTPException(status_code=401, detail="No autenticado")
    
    session_email = session_user.get("email")
    if not session_email:
        raise HTTPException(status_code=401, detail="No autenticado")

    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get empresa ID from session email
            cur.execute("""
                SELECT e.ID_Empresa
                FROM EMPRESA e
                JOIN USUARIO u ON e.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
            """, (session_email,))
            empresa = cur.fetchone()
            
            if not empresa:
                raise HTTPException(status_code=404, detail="Empresa no encontrada")
            
            id_empresa = empresa["id_empresa"]
            
            # Verify vacancy ownership
            cur.execute("""
                SELECT ID_Vacante
                FROM VACANTE
                WHERE ID_Vacante = %s AND FK_ID_Empresa = %s
                LIMIT 1;
            """, (id_vacante, id_empresa))
            
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Vacante no encontrada o no autorizada")
            
            # Build dynamic update query based on provided fields
            update_fields = []
            params = []
            
            if data.titulo is not None:
                update_fields.append("Titulo = %s")
                params.append(data.titulo)
            
            if data.descripcion is not None:
                update_fields.append("Descripcion = %s")
                params.append(data.descripcion)
            
            if data.salario is not None:
                update_fields.append("Salario = %s")
                params.append(data.salario)
            
            if data.modalidad is not None:
                update_fields.append("Modalidad = %s")
                params.append(data.modalidad)
            
            if data.estado is not None:
                # Validate estado
                if data.estado not in ['Borrador', 'Publicada', 'Cerrada']:
                    raise HTTPException(status_code=400, detail="Estado inválido")
                update_fields.append("Estado = %s")
                params.append(data.estado)
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="No hay campos para actualizar")
            
            # Add vacancy ID to params
            params.append(id_vacante)
            
            # Execute update
            query = f"""
                UPDATE VACANTE
                SET {', '.join(update_fields)}
                WHERE ID_Vacante = %s
                RETURNING ID_Vacante;
            """
            
            cur.execute(query, params)
            conn.commit()
            
            logger.info(f"Vacante {id_vacante} actualizada exitosamente")
            return {"message": "Vacante actualizada exitosamente", "id_vacante": id_vacante}
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error update_vacante: {e}")
        raise HTTPException(status_code=500, detail="Error interno actualizando la vacante")
    finally:
        conn.close()


# --- Endpoint para registro de empresa multipart (pasos 1-3 flujo) ---
@app.post("/api/register_employer/")
async def register_employer(
    email: str = Form(...),
    password: str = Form(...),
    nombre_empresa: str = Form(...),
    ruc: str = Form(...),  # ahora obligatorio
    categoria: str = Form(""),
    descripcion: str = Form(""),
    logo: UploadFile | None = File(None)
):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")

    # Validaciones básicas: email, password y RUC obligatorio/formato
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email inválido.")
    if not is_valid_password(password):
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 8 caracteres, al menos una letra, una mayúscula y un número.")
    # RUC ahora requerido y validado
    if not ruc or not is_valid_ruc_ec(ruc):
        raise HTTPException(status_code=400, detail="RUC inválido. Debe ser 13 dígitos y comenzar con código provincial válido (01-24).")

    # Verificar duplicados antes de insertar
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM USUARIO WHERE Email = %s LIMIT 1;", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email ya registrado.")
            cur.execute("SELECT 1 FROM EMPRESA WHERE RUC = %s LIMIT 1;", (ruc,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="RUC ya registrado.")
    finally:
        # no cerramos la conexión aquí, se usa luego
        pass

    logo_bytes = await logo.read() if logo else None
    hashed_password = hash_password(password)

    try:
        # Transacción: insertar usuario + empresa
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO USUARIO (Email, Password, Rol)
                    VALUES (%s, %s, %s)
                    RETURNING ID_Usuario;
                    """,
                    (email, hashed_password, 'Empresa')
                )
                row = cur.fetchone()
                if not row:
                    raise Exception("No se obtuvo ID_Usuario tras INSERT.")
                user_id = row[0]

                cur.execute(
                    """
                    INSERT INTO EMPRESA (FK_ID_Usuario, Foto_Logo_BIN, Nombre_Empresa, RUC, Categoria, Descripcion)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING ID_Empresa;
                    """,
                    (
                        user_id,
                        psycopg2.Binary(logo_bytes) if logo_bytes else None,
                        nombre_empresa,
                        ruc or None,
                        categoria or None,
                        descripcion or None
                    )
                )
                empresa_row = cur.fetchone()
                if not empresa_row:
                    raise Exception("No se obtuvo ID_Empresa tras INSERT.")
                empresa_id = empresa_row[0]

        return {"message": "Empresa registrada exitosamente", "user_id": user_id, "empresa_id": empresa_id}

    except psycopg2.IntegrityError as e:
        # transacción revertida automáticamente por 'with conn'
        conn.rollback()
        detail = ""
        try:
            detail = (e.diag.message_detail or "").lower()
        except Exception:
            detail = str(e).lower()
        if "ruc" in detail:
            msg = "RUC ya registrado."
        elif "email" in detail:
            msg = "Email ya registrado."
        else:
            msg = "Email o RUC ya registrado."
        raise HTTPException(status_code=400, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        print("Error register_employer:", e)
        raise HTTPException(status_code=500, detail="Error interno durante el registro de empresa.")
    finally:
        try:
            conn.close()
        except Exception:
            pass

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

    # Validaciones
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email inválido.")
    if not is_valid_password(password):
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 8 caracteres, al menos una letra, una mayúscula y un número.")

    # Verificar duplicado de email
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM USUARIO WHERE Email = %s LIMIT 1;", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="El email ya está registrado.")
    except HTTPException:
        raise

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


# ===== Validadores (necesarios para endpoints) =====
import re
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")
# RUC Ecuador (simplificado): 13 dígitos, provincia 01-24
RUC_EC_REGEX = re.compile(r"^(?:0[1-9]|1[0-9]|2[0-4])\d{11}$")

def is_valid_email(email: str) -> bool:
    try:
        return bool(email and EMAIL_REGEX.match(email))
    except Exception:
        return False

def is_valid_password(pw: str) -> bool:
    """Comprueba: >=8 chars, al menos 1 mayúscula, 1 minúscula y 1 dígito."""
    try:
        if not pw or len(pw) < 8:
            return False
        has_upper = any(c.isupper() for c in pw)
        has_lower = any(c.islower() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        return has_upper and has_lower and has_digit
    except Exception:
        return False

def is_valid_ruc_ec(ruc: str) -> bool:
    try:
        return bool(ruc and RUC_EC_REGEX.match(ruc))
    except Exception:
        return False

# ----------------------------------------------------
# 5. Vacantes públicas y postulaciones (Candidato)
# ----------------------------------------------------

@app.get("/ver-aplicaciones", response_class=HTMLResponse)
async def ver_aplicaciones_page():
    """Página para que el candidato vea vacantes y pueda postular."""
    return _serve_static_html("Ver-aplicaciones.html", "Ver Aplicaciones")

@app.get("/api/vacantes/publicadas")
async def listar_vacantes_publicadas(request: Request, search: str | None = None):
    """Lista todas las vacantes publicadas visibles para candidatos.
    Opcionalmente filtra por texto en título, descripción, modalidad o nombre de empresa.
    Incluye conteo de postulaciones actuales."""
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            base_sql = """
                SELECT v.ID_Vacante, v.Titulo, v.Descripcion, v.Salario, v.Modalidad, v.Estado, v.Fecha_Creacion,
                       e.Nombre_Empresa,
                       COALESCE(COUNT(p.ID_Postulacion), 0) AS num_postulaciones
                FROM VACANTE v
                JOIN EMPRESA e ON v.FK_ID_Empresa = e.ID_Empresa
                LEFT JOIN POSTULACION p ON p.FK_ID_Vacante = v.ID_Vacante
                WHERE v.Estado = 'Publicada'
            """
            params = []
            if search:
                base_sql += (
                    " AND (LOWER(v.Titulo) LIKE %s OR LOWER(v.Descripcion) LIKE %s OR LOWER(v.Modalidad) LIKE %s OR LOWER(e.Nombre_Empresa) LIKE %s)"
                )
                s = f"%{search.lower()}%"
                params.extend([s, s, s, s])
            # Importante: incluir TODAS las columnas seleccionadas (no agregadas) en el GROUP BY para Postgres
            base_sql += " GROUP BY v.ID_Vacante, v.Titulo, v.Descripcion, v.Salario, v.Modalidad, v.Estado, v.Fecha_Creacion, e.Nombre_Empresa ORDER BY v.Fecha_Creacion DESC"
            cur.execute(base_sql, params)
            rows = cur.fetchall() or []
            vacantes = []
            for r in rows:
                vacantes.append({
                    "id_vacante": r["id_vacante"],
                    "titulo": r["titulo"],
                    "descripcion": r["descripcion"],
                    "salario": float(r["salario"]) if r.get("salario") is not None else None,
                    "modalidad": r["modalidad"],
                    "estado": r["estado"],
                    "fecha_creacion": r["fecha_creacion"].isoformat() if r["fecha_creacion"] else None,
                    "nombre_empresa": r["nombre_empresa"],
                    "num_postulaciones": int(r["num_postulaciones"]) if r.get("num_postulaciones") is not None else 0
                })
            return {"vacantes": vacantes}
    except Exception as e:
        print("Error listar_vacantes_publicadas:", e)
        raise HTTPException(status_code=500, detail="Error interno listando vacantes")
    finally:
        try: conn.close()
        except Exception: pass

@app.post("/api/vacantes/{id_vacante}/postular")
async def postular_a_vacante(id_vacante: int, request: Request):
    """Permite a un candidato autenticado postular a una vacante publicada."""
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or session_user.get("rol") != "Candidato":
        raise HTTPException(status_code=401, detail="Solo candidatos pueden postular")
    email = session_user.get("email")
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Obtener ID_Candidato
            cur.execute("""
                SELECT c.ID_Candidato
                FROM USUARIO u
                JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
            """, (email,))
            cand = cur.fetchone()
            if not cand:
                raise HTTPException(status_code=404, detail="Perfil de candidato no encontrado")
            id_cand = cand["id_candidato"]
            # Validar existencia y estado de la vacante
            cur.execute("""
                SELECT Estado FROM VACANTE WHERE ID_Vacante = %s LIMIT 1;
            """, (id_vacante,))
            vrow = cur.fetchone()
            if not vrow or vrow["estado"] != "Publicada":
                raise HTTPException(status_code=404, detail="Vacante no disponible para postular")
            # Insertar postulacion (única por candidato/vacante)
            try:
                cur.execute("""
                    INSERT INTO POSTULACION (FK_ID_Candidato, FK_ID_Vacante)
                    VALUES (%s, %s)
                    RETURNING ID_Postulacion;
                """, (id_cand, id_vacante))
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(status_code=400, detail="Ya postulaste a esta vacante")
            pid = cur.fetchone()["id_postulacion"]
            conn.commit()
            return {"message": "Postulación registrada", "id_postulacion": pid}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        print("Error postular_a_vacante:", e)
        raise HTTPException(status_code=500, detail="Error interno al postular")
    finally:
        try: conn.close()
        except Exception: pass

@app.get("/api/postulaciones/mias")
async def listar_postulaciones_candidato(request: Request):
    """Devuelve las postulaciones del candidato autenticado."""
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not session_user or session_user.get("rol") != "Candidato":
        raise HTTPException(status_code=401, detail="Solo candidatos")
    email = session_user.get("email")
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la DB")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.ID_Candidato
                FROM USUARIO u
                JOIN CANDIDATO c ON c.FK_ID_Usuario = u.ID_Usuario
                WHERE u.Email = %s
                LIMIT 1;
            """, (email,))
            cand = cur.fetchone()
            if not cand:
                raise HTTPException(status_code=404, detail="Candidato no encontrado")
            id_cand = cand["id_candidato"]
            cur.execute("""
                SELECT p.ID_Postulacion, p.Fecha_Postulacion, p.Estado_Proceso,
                       v.ID_Vacante, v.Titulo, e.Nombre_Empresa
                FROM POSTULACION p
                JOIN VACANTE v ON p.FK_ID_Vacante = v.ID_Vacante
                JOIN EMPRESA e ON v.FK_ID_Empresa = e.ID_Empresa
                WHERE p.FK_ID_Candidato = %s
                ORDER BY p.Fecha_Postulacion DESC;
            """, (id_cand,))
            rows = cur.fetchall() or []
            postulaciones = []
            for r in rows:
                postulaciones.append({
                    "id_postulacion": r["id_postulacion"],
                    "fecha_postulacion": r["fecha_postulacion"].isoformat() if r["fecha_postulacion"] else None,
                    "estado_proceso": r["estado_proceso"],
                    "id_vacante": r["id_vacante"],
                    "titulo": r["titulo"],
                    "nombre_empresa": r["nombre_empresa"]
                })
            return {"postulaciones": postulaciones}
    except Exception as e:
        print("Error listar_postulaciones_candidato:", e)
        raise HTTPException(status_code=500, detail="Error interno listando postulaciones")
    finally:
        try: conn.close()
        except Exception: pass
