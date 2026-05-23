# Contribuir a VanguardOps

¡Gracias por tu interés! Esta guía explica cómo configurar el entorno, las convenciones que seguimos y cómo abrir un Pull Request que pase CI a la primera.

## 1 · Preparar el entorno

```bash
git clone https://github.com/0xvanguard/VanguardOps.git
cd VanguardOps

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
```

> Necesitas Python **3.12+**. El proyecto se prueba en CI contra Linux con esa versión exacta.

## 2 · Flujo de trabajo

1. Crea una rama desde `main`:
   ```bash
   git checkout -b feat/<descripcion-corta>     # o fix/, chore/, docs/
   ```
2. Realiza tus cambios siguiendo las [convenciones de código](#5--convenciones-de-código).
3. Asegúrate de que `make check` pasa localmente.
4. Abre un Pull Request contra `main`.

## 3 · Convenciones de commit

Usamos **[Conventional Commits](https://www.conventionalcommits.org/)** para que los changelogs y la cronología sean legibles:

```
<type>(<scope>): <descripción imperativa, ≤72 chars>

<cuerpo opcional explicando el "por qué">

<footer opcional: BREAKING CHANGE, refs #123>
```

`type` admitidos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `perf`, `build`, `style`.

**Ejemplos buenos:**

```
feat(tickets): enforce state-machine on PATCH /tickets/{id}
fix(workers): atomic claim avoids double execution under load
refactor(crud): drop jsonable_encoder in CRUDBase.create
```

## 4 · Pull Request checklist

Antes de marcar el PR como _ready for review_:

- [ ] `make lint` sin errores.
- [ ] `make test` verde (60+ tests).
- [ ] Cobertura ≥ 75 % (CI lo valida).
- [ ] Si tocaste el modelo, hay una migración Alembic.
- [ ] Si añadiste una variable de entorno, está en `.env.example`.
- [ ] El título del PR sigue Conventional Commits (será el squash commit).
- [ ] Descripción del PR incluye: **qué cambia**, **por qué**, **cómo se probó**.

## 5 · Convenciones de código

### Python

* **Type hints obligatorios** en funciones públicas y métodos de servicio.
* **Pydantic v2** para validación de entrada/salida.
* **SQLAlchemy 2.0** con `Mapped[...]` y `mapped_column(...)`.
* `from __future__ import annotations` al tope de cada módulo.
* Excepciones de dominio heredan de `app.core.exceptions.VanguardOpsError`.
* No usar `print` ni `logging` directo en código nuevo: usar `app.core.logging.get_logger(__name__)`.
* No leer `os.environ` fuera de `app.core.config`.

### Tests

* Usar `factory-boy` (ver `tests/factories.py`) en lugar de objetos manuales.
* Cada test debe ser **aislado e idempotente** (la fixture `db_session` ya garantiza rollback).
* Para autenticación usar `admin_headers` / `operator_headers` / `viewer_headers`.
* Probar siempre el _happy path_ y al menos un caso de error.

### Frontend

* Sin frameworks ni build step (vanilla ES modules).
* Toda llamada a la API pasa por el helper `api()` (gestiona JWT y refresh).
* Renderizado: HTML por strings con `escapeHtml(...)` siempre que el dato venga del servidor.

## 6 · Estructura de un PR de feature típico

```
feat(<scope>): título corto

Contexto / motivación
---------------------
- Por qué hace falta este cambio.
- Decisiones de diseño relevantes.

Qué cambia
----------
- Lista breve.

Cómo se probó
-------------
- Tests añadidos: ...
- Manual: pasos.

Notas para el revisor
---------------------
- Riesgos, follow-ups, links a ADRs.
```

## 7 · Reportar un bug

Abre un _issue_ con:

* Pasos exactos para reproducir.
* Comportamiento esperado vs observado.
* Versión (`/livez` devuelve la versión).
* Logs relevantes con su `X-Request-ID`.

¡Gracias por contribuir! 🚀
