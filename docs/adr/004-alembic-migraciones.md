# ADR-004: Migraciones gestionadas con Alembic (sin `create_all` en runtime)

* Estado: Aceptado · revisado para hardening
* Fecha: 2026-05-23

## Contexto

La versión inicial llamaba a `Base.metadata.create_all(engine)` en cada arranque de la API. Esto:

* No registra el historial de cambios del schema (no se sabe en qué versión está cada entorno).
* No permite migraciones reversibles ni cambios destructivos controlados.
* Hace imposible un rollback ordenado en producción.
* En entornos compartidos puede crear índices/columnas que después Alembic no detecta como diff, llevando a divergencia silenciosa.

## Opciones consideradas

1. **Mantener `create_all`** en arranque: solo viable para demos.
2. **Scripts SQL manuales**: factibles pero propensos a errores y desincronización con el ORM.
3. **Alembic** (estándar SQLAlchemy): autogenera revisiones a partir del modelo, soporta `upgrade`/`downgrade`, integra con CI/CD.

## Decisión

Adoptamos **Alembic** como única vía de manipulación del schema:

* `alembic/env.py` lee la URL de la BD desde `app.core.config.get_settings()`, así no se duplica configuración.
* Usamos un **naming convention** explícito en `MetaData` (en `app/database.py`) para que los nombres de constraints/indexes sean deterministas y portables entre PostgreSQL y SQLite.
* `compare_type=True` y `compare_server_default=True` para que `--autogenerate` detecte cambios reales.

**Regla operacional crítica:** `Base.metadata.create_all(...)` **no se llama nunca en el lifespan de la app**. El `lifespan` de FastAPI solo ejecuta `bootstrap_admin()`. Cualquier cambio de schema debe pasar por una revisión Alembic versionada.

* En **producción / staging** el comando de arranque del contenedor encadena `alembic upgrade head && uvicorn ...` (ver `docker-compose.yml` y futuros Helm charts). Si la migración falla, el container falla y Kubernetes/Compose no envía tráfico.
* En **desarrollo local** los devs corren `make migrate` (que ejecuta `alembic upgrade head`) tras un `pull`.
* En **tests**, `tests/conftest.py` construye un schema efímero con `Base.metadata.create_all` sobre una BD SQLite en memoria. Esta es la **única** ruta donde `create_all` aparece, y está aislada del runtime de la aplicación.

## Consecuencias

* ✅ Cada cambio de schema es una revisión versionada en `alembic/versions/`.
* ✅ CI puede correr `alembic upgrade head` contra una BD vacía como humo de contrato.
* ✅ Naming convention significa que `alembic revision --autogenerate` produce diffs limpios.
* ✅ Imposible "shadow create" en runtime: si un dev añade una columna sin migración, la app falla en producción al ejecutar el INSERT/SELECT correspondiente, en lugar de "auto-corregir" silenciosamente el schema.
* ⚠️ Los desarrolladores deben generar la revisión cuando tocan un modelo (`make revision m="..."`); el checklist del PR (CONTRIBUTING.md) lo refuerza, y una verificación opcional en CI puede correr `alembic check` para detectar diffs no commiteados.
