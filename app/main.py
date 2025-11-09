import os
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import re

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
async def login_user(email: str = Form(...), password: str = Form(...)):
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
        

# --- Crear Vacante ---
class VacanteCreate(BaseModel):
    titulo: str
    descripcion: str | None = None
    salario: float | None = None
    modalidad: str
    # Para identificar a qué empresa pertenece la vacante:
    empresa_email: str  # email del USUARIO dueño de la EMPRESA

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

    # Validaciones básicas
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email inválido.")
    if not is_valid_password(password):
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 8 caracteres, al menos una letra, una mayúscula y un número.")
    if ruc:
        if not is_valid_ruc_ec(ruc):
            raise HTTPException(status_code=400, detail="RUC inválido. Debe ser 13 dígitos y comenzar con código de provincia válido (01-24).")

    # Verificar duplicados antes de insertar
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM USUARIO WHERE Email = %s LIMIT 1;", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email ya registrado.")
            if ruc:
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
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")
#PASSWORD_REGEX = re.compile(r"^(?=.*[A-Z])(?=.*[a-zA-Z])(?=.*\d).{8,}$")  # <-- removed usage
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
