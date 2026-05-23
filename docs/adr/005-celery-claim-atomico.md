# ADR-005: Claim atómico para evitar ejecución doble de workflows

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

La implementación inicial transitaba el estado de un workflow así:

```python
workflow = crud.workflow.get(db, id=wf_id)
if workflow.status != PENDING:
    return  # skip
workflow.status = RUNNING
db.commit()
```

Bajo carga, dos workers de Celery podían **leer ambos `PENDING`** antes de que ninguno hiciera commit, y terminar ejecutando el mismo workflow dos veces. Es la clásica condición TOCTOU (_Time-of-check to time-of-use_).

## Opciones consideradas

1. **Lock pesimista con `SELECT FOR UPDATE`**: funciona en PostgreSQL pero exige una transacción larga y bloquea filas.
2. **Lock distribuido con Redis** (`SETNX` con TTL): añade dependencia explícita, complica los tests.
3. **`UPDATE ... WHERE status IN (...)` condicional**: una sola sentencia atómica, soportada por todos los backends, sin lock prolongado.

## Decisión

Implementamos `crud.workflow.claim_for_execution(workflow_id)`:

```python
stmt = (
    update(Workflow)
    .where(
        Workflow.id == workflow_id,
        Workflow.status.in_([PENDING, RETRYING]),
    )
    .values(status=RUNNING)
)
result = db.execute(stmt); db.commit()
return db.get(Workflow, workflow_id) if result.rowcount else None
```

Un `rowcount == 0` significa "otro worker me ganó" → la tarea registra `workflow_skipped_duplicate` y termina sin efecto.

## Consecuencias

* ✅ Idempotencia real: dos invocaciones simultáneas de la misma task ejecutan el workflow exactamente una vez.
* ✅ Compatible con SQLite (tests) y PostgreSQL (prod).
* ✅ Sin overhead de locking distribuido.
* ⚠️ La función Celery no debe asumir que recibe el workflow en estado PENDING; siempre comprueba el resultado del claim.
