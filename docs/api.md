# Resumen del contrato HTTP

> El contrato canónico es el OpenAPI generado en runtime: <http://localhost:8000/api/v1/openapi.json>.
> Esta página resume la **forma** del API y los **códigos de error estables**.

## Convenciones generales

* Versión actual: `v1`. Todas las rutas viven bajo `/api/v1/*`.
* Las respuestas son JSON salvo `/metrics` (`text/plain; version=0.0.4`).
* Las fechas son ISO-8601 con offset UTC (`2026-05-23T10:00:00Z`).
* Los listados paginados devuelven el sobre `Page[T]`:

  ```json
  {
    "items": [...],
    "total": 124,
    "page": 1,
    "size": 20,
    "has_next": true,
    "has_prev": false
  }
  ```

* Cada respuesta trae el header `X-Request-ID`. Si tu cliente lo envía, se respeta; si no, se genera.

## Autenticación

| Método | Ruta | Cuerpo | Auth |
|--------|------|--------|------|
| POST | `/api/v1/auth/login` | `{ email, password }` | — |
| POST | `/api/v1/auth/login/oauth` | form `username` + `password` | — |
| POST | `/api/v1/auth/refresh` | `{ refresh_token }` | — |
| POST | `/api/v1/auth/register` | `UserCreate` | admin |
| POST | `/api/v1/auth/logout` | `{ refresh_token? }` (opcional) | cualquier rol |
| GET | `/api/v1/auth/me` | — | cualquier rol |

Header en endpoints protegidos: `Authorization: Bearer <access_token>`.

## Recursos

| Método | Ruta | Rol mínimo | Notas |
|--------|------|------------|-------|
| POST | `/api/v1/assets/` | operator | Crear asset |
| GET | `/api/v1/assets/` | viewer | Listado paginado |
| GET | `/api/v1/assets/{id}` | viewer | |
| GET | `/api/v1/assets/by-ip/{ip}` | viewer | |
| GET | `/api/v1/assets/by-status/{status}` | viewer | |
| PATCH | `/api/v1/assets/{id}` | operator | |
| POST | `/api/v1/tickets/` | operator | Calcula priority + due_at + assignee. Dispara workflow si la categoría aplica. |
| GET | `/api/v1/tickets/` | viewer | |
| GET | `/api/v1/tickets/filter` | viewer | Filtros: `status_value`, `severity`, `priority`, `asset_id` |
| GET | `/api/v1/tickets/{id}` | viewer | |
| PATCH | `/api/v1/tickets/{id}` | operator | Aplica state machine |
| POST | `/api/v1/workflows/` | operator | Crea con estado `PENDING` |
| GET | `/api/v1/workflows/` | viewer | |
| GET | `/api/v1/workflows/{id}` | viewer | |
| GET | `/api/v1/workflows/by-ticket/{id}` | viewer | |
| GET | `/api/v1/workflows/by-status/{status}` | viewer | |
| GET | `/api/v1/activity-log/` | viewer | Timeline global (newest first) |
| GET | `/api/v1/activity-log/{entity}/{id}` | viewer | Timeline por entidad |

## State machine de Tickets

```
OPEN ──▶ IN_PROGRESS ──▶ RESOLVED ──▶ CLOSED
 │              │              │
 └──────────▶ CLOSED       (back to IN_PROGRESS)
                    (back to OPEN)
```

Cualquier transición no contemplada responde **409 Conflict** con `code: "invalid_state_transition"`.

## Códigos de error estables

| HTTP | `code` | Significado |
|------|--------|-------------|
| 400 | `bad_request` | Petición malformada (no validation) |
| 401 | `invalid_credentials` | Token ausente, inválido, expirado, o login fallido |
| 403 | `forbidden` | Autenticado pero el rol no es suficiente |
| 404 | `not_found`, `ticket_not_found`, `asset_not_found`, `workflow_not_found` | El recurso no existe |
| 409 | `conflict` | Genérico |
| 409 | `invalid_state_transition` | Cambio de estado no permitido |
| 409 | `user_already_exists` | Email duplicado en registro |
| 422 | `validation_error` | Pydantic rechazó la entrada (incluye `errors[]`) |
| 429 | `rate_limited` | Excedido el límite configurado |
| 500 | `internal_error` | Inesperado, ya está logueado por el servidor |

## Observabilidad

* `GET /livez` — proceso vivo (sin dependencias).
* `GET /readyz` — DB y Redis responden.
* `GET /metrics` — Prometheus (`http_requests_total`, `http_request_duration_seconds`).
* `GET /docs` — Swagger UI.
* `GET /redoc` — ReDoc.

## Ejemplos rápidos

```bash
# Login
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@vanguardops.local","password":"ChangeMe!2024"}' \
  | jq -r .access_token)

# Crear asset
curl -X POST localhost:8000/api/v1/assets/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"web-01","asset_type":"SERVER","ip_address":"10.0.0.10"}'

# Crear ticket
curl -X POST localhost:8000/api/v1/tickets/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Reset password","description":"User locked out",
       "category":"password_reset","severity":"MEDIUM"}'
```
