# ADR-001: Arquitectura en capas (api / services / crud / models)

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

VanguardOps debe sostener varias responsabilidades cruzadas (validación, reglas de negocio, persistencia, ejecución asíncrona, auditoría) sin convertirse en una pelota de barro. Necesitamos una división donde:

* La lógica de negocio sea **probable sin levantar HTTP** ni un broker.
* Los endpoints sean **delgados** para no enredar transporte con dominio.
* Los workers de Celery puedan **reusar la misma lógica** que la API sin duplicación.

## Opciones consideradas

1. **Mono-archivo / scripts**: rápido para prototipos, imposible de mantener.
2. **MVC clásico**: agrupa por tipo de archivo (todos los models juntos, todos los controllers juntos), pero mezcla negocio con persistencia.
3. **Capas explícitas (Hexagonal-lite)**: separar `api/` (transporte) → `services/` (dominio) → `crud/` (persistencia) → `models/` (esquema).

## Decisión

Adoptamos la **opción 3**, con cuatro capas y una regla de dirección:

```
api  →  services  →  crud  →  models
        services  ←  workers (reutilizan dominio)
```

Reglas:

* `api/` solo conoce a `services/` y `crud/`. Nunca SQL ni reglas inline.
* `services/` no importa nada de FastAPI; recibe `Session` por parámetro y devuelve modelos / valores.
* `crud/` ofrece operaciones CRUD genéricas y consultas; nunca contiene lógica de negocio (ej. cálculo de SLA).
* `models/` define el esquema y _state machines_ declarativos (`TICKET_STATE_MACHINE`).
* `workers/` reutiliza `services/` y `crud/`.

## Consecuencias

* ✅ Tests unitarios de reglas (`tests/test_rules.py`) corren en milisegundos sin DB.
* ✅ Cambiar el transporte (REST → GraphQL → gRPC) afectaría sólo `api/`.
* ✅ Los workers comparten la misma `auditoría` y `state machine` que la API.
* ⚠️ Hay algo de boilerplate: cada entidad nueva implica modelo + schema + crud + servicio + endpoint. Aceptado a cambio de claridad.
