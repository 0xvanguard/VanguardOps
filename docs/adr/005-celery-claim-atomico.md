# ADR-005: Bloqueo pesimista para evitar ejecución doble de workflows

* Estado: Aceptado · supersede al borrador inicial (UPDATE atómico)
* Fecha: 2026-05-23

## Contexto

La implementación inicial transitaba el estado de un workflow así:

```python
workflow = crud.workflow.get(db, id=wf_id)
if workflow.status != PENDING:
    return                      # skip
workflow.status = RUNNING
db.commit()
```

Bajo carga, dos workers de Celery podían **leer ambos `PENDING`** antes de que ninguno hiciera commit, y terminar ejecutando el mismo workflow dos veces. Es la clásica condición TOCTOU (_Time-of-check to time-of-use_).

Un primer fix usó `UPDATE Workflow SET status='RUNNING' WHERE id=:id AND status IN ('PENDING','RETRYING')` y se basó en `rowcount`. Es atómico, pero:

* No expone semántica de "lock" al motor: el row no queda bloqueado durante la siguiente lectura, y otra transacción larga puede tocarlo entre el UPDATE y el siguiente SELECT.
* No es la pieza idiomática que un DBA espera ver en una tabla-cola.

## Opciones consideradas

1. **`UPDATE ... WHERE status IN (...)`**: atómico, simple, pero no expresa lock.
2. **Lock distribuido en Redis** (`SETNX` con TTL): añade una dependencia explícita y hay que afinar el TTL para no liberar locks prematuramente cuando una task tarda más de lo previsto.
3. **`SELECT ... FOR UPDATE SKIP LOCKED`**: el patrón canónico de tabla-cola en PostgreSQL. El lock vive solo durante la transacción del *claim*, no durante la ejecución del workflow.

## Decisión

`crud.workflow.claim_for_execution(workflow_id)` ahora ejecuta:

```python
stmt = (
    select(Workflow)
    .where(
        Workflow.id == workflow_id,
        Workflow.status.in_([PENDING, RETRYING]),
    )
    .with_for_update(skip_locked=True)
)
workflow = db.execute(stmt).scalar_one_or_none()
if workflow is None:
    db.rollback()
    return None
workflow.status = RUNNING
db.commit()           # libera el lock
return workflow
```

`scalar_one_or_none()` devuelve `None` por **tres** razones desde el punto de vista del worker:

* la fila no existe,
* otro worker ya la tiene bloqueada (`SKIP LOCKED` la oculta),
* la fila está en estado terminal o `RUNNING`.

El worker, al recibir `None`, hace una segunda lectura sin lock (`db.get(Workflow, id)`) **solo para auditoría** y registra `workflow_skipped_duplicate`.

El ciclo de ejecución del worker se divide en tres transacciones cortas:

1. **Claim** (con `FOR UPDATE SKIP LOCKED`) → marca `RUNNING` y commit.
2. **Run** (sin lock) → ejecuta el workflow body.
3. **Persist** → marca `SUCCESS` o `FAILED` y commit.

Cada fase abre una `Session` distinta dentro de un `with SessionLocal() as db:`, garantizando cierre incluso ante fallos abruptos de Celery (ver ADR-006).

## Consecuencias

* ✅ Idempotencia real bajo concurrencia: dos invocaciones simultáneas ejecutan el workflow exactamente una vez.
* ✅ El lock de fila se libera *antes* de la ejecución, así un workflow lento no impide reclamar otros.
* ✅ Compatible con SQLite (tests): SQLAlchemy ignora silenciosamente `with_for_update`, lo cual es seguro porque los tests son single-writer.
* ⚠️ Requiere PostgreSQL en producción para que `SKIP LOCKED` realmente bloquee filas en concurrencia. MySQL 8+ también lo soporta; lo documentamos en el README.
