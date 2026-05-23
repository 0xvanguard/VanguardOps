# ADR-002: Errores HTTP en formato RFC 7807

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

FastAPI por defecto serializa los errores como `{"detail": "..."}`. Eso obliga a los clientes a parsear strings, no es estable, y no ofrece un identificador estable para ramificar. Una API senior:

* Necesita un esquema de error único y predecible.
* Debe poder añadir información extra (campos rechazados, transiciones permitidas) sin romper clientes existentes.
* Debe correlacionar errores con logs vía `request_id`.

## Opciones consideradas

1. **Formato propio JSON ad-hoc**: rápido, pero no estandarizado.
2. **JSON:API errors**: cubre el caso, pero el resto del API no es JSON:API.
3. **RFC 7807 (`application/problem+json`)**: estándar IETF, soportado por OpenAPI, ampliamente usado en industria (Stripe, GitHub, Microsoft Graph).

## Decisión

Adoptamos **RFC 7807**. Cada error responde con `Content-Type: application/problem+json` y el siguiente cuerpo:

```json
{
  "type": "https://errors.vanguardops.dev/<code>",
  "title": "Human-readable title",
  "status": 409,
  "detail": "Specific message for this occurrence",
  "code": "stable_machine_readable_code",
  "instance": "/api/v1/<path>",
  "request_id": "<uuid>",
  "<extension fields>": "..."
}
```

Implementación:

* Una jerarquía `VanguardOpsError` en `app/core/exceptions.py` con subclases por dominio (`TicketNotFoundError`, `InvalidStateTransitionError`, etc.).
* Handlers FastAPI globales en `app/core/error_handlers.py` mapean cualquier excepción a esta forma.
* Validación 422 incluye los `errors[]` con `{loc, msg, type}` para que el frontend pueda resaltar campos.

## Consecuencias

* ✅ Clientes pueden ramificar por `code` sin acoplarse a textos.
* ✅ El `request_id` permite correlacionar el error con los logs estructurados.
* ✅ Documentado automáticamente en OpenAPI vía `responses={...}` en `create_app`.
* ⚠️ Hay que mantener la lista de `code`s estables; documentarla en `docs/api.md`.
