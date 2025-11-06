# Jobly — minimal FastAPI + static frontend starter

Estructura mínima para una app web con backend en FastAPI (REST) y frontend en HTML/CSS estático. Pensada para desplegar en Railway con una base de datos PostgreSQL ya provisionada.

Archivos clave:
- `app/` - código del backend y archivos estáticos (index.html, css).
- `Procfile` - comando de arranque para Railway.
- `requirements.txt` - dependencias Python.
- `.env.example` - ejemplo de variables de entorno (no subir secretos).

Rápido `run` local (Windows / Git Bash):

```bash
# instalar dependencias
python -m pip install -r requirements.txt

# crear .env copiando .env.example y ajustando DATABASE_URL (opcional localmente puedes usar sqlite por defecto)
cp .env.example .env

# arrancar en modo desarrollo
uvicorn app.main:app --reload --port 8000
```

Endpoints útiles:
- `GET /api/items` - lista items
- `POST /api/items` - crea item (JSON: {"title": "...", "description": "..."})
- `GET /` - página estática `index.html`

Railway deployment notes:

1. Crea un proyecto y añade tu repo.
2. Añade el plugin de Postgres (si ya tienes la DB, copia la `DATABASE_URL`).
3. En Settings > Environment variables, asegúrate de que `DATABASE_URL` está presente.
4. Railway detectará `Procfile` y ejecutará el comando `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Notas:
- Para producción considera usar migraciones (Alembic) en lugar de `create_all`.
- No comitees tu archivo `.env` con credenciales.
