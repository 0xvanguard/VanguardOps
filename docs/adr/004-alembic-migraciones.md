# ADR-004: Migraciones gestionadas con Alembic

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

La versión anterior llamaba a `Base.metadata.create_all(engine)` en cada arranque. Esto:

* No registra el historial de cambios del schema (no se sabe en qué versión está cada entorno).
* No permite migraciones reversibles ni cambios destructivos controlados.
* Hace imposible un rollback ordenado en producción.

## Opciones consideradas

1. **Mantener `create_all`**: solo viable para demos.
2. **Scripts SQL manuales**: factibles pero propensos a errores y desincronización con el ORM.
3. **Alembic** (estándar SQLAlchemy): autogenera revisiones a partir del modelo, soporta `upgrade`/`downgrade`, integra con CI/CD.

## Decisión

Adoptamos **Alembic** con la siguiente configuración:

* `alembic/env.py` lee la URL de la BD desde `app.core.config.get_settings()`, así no se duplica configuración.
* Usamos un **naming convention** explícito en `MetaData` (en `app/database.py`) para que los nombres de constraints/indexes sean deterministas y portables entre PostgreSQL y SQLite.
* `compare_type=True` y `compare_server_default=True` para detectar cambios reales en autogeneración.
* Los entornos `development` y `test` siguen usando `Base.metadata.create_all` en arranque (vía `bootstrap.ensure_schema`) por velocidad. Producción ejecuta `alembic upgrade head` antes de levantar uvicorn (ver `docker-compose.yml` y futuro Helm chart).

## Consecuencias

* ✅ Cada cambio de schema es una revisión versionada en `alembic/versions/`.
* ✅ CI puede correr `alembic upgrade head` contra una BD vacía como humo de contrato.
* ✅ Naming convention significa que `alembic revision --autogenerate` produce diffs limpios.
* ⚠️ Los desarrolladores deben generar la revisión cuando tocan un modelo (`make revision m="..."`); aplicado por el checklist del PR (CONTRIBUTING.md).
