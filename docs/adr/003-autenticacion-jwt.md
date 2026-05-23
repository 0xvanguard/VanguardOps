# ADR-003: Autenticación basada en JWT con roles

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

La versión inicial usaba un único header fijo `X-Admin-Token` con valor hardcoded en código (`super-secret-admin-token`). Esto:

* No distingue usuarios.
* No es revocable.
* No soporta roles.
* Está en repositorio público.

Necesitamos un esquema que:

1. Identifique al usuario individualmente.
2. Soporte tres niveles de privilegio (`viewer`, `operator`, `admin`).
3. No requiera infraestructura externa adicional (no Keycloak en MVP).
4. Sea trivialmente integrable con clientes (curl, frontend, CI).

## Opciones consideradas

1. **API keys por usuario en BD**: simple, pero exige hit a BD por request y no expira solo.
2. **OAuth 2.0 con un IdP externo (Keycloak / Auth0)**: enterprise, pero suma una pieza de infraestructura para un MVP.
3. **JWT propio (HS256)** con access + refresh tokens: estándar, sin estado, fácil de adoptar.

## Decisión

Implementamos **JWT propio** con dos tipos de tokens:

| Token | Vida | Uso |
|-------|------|-----|
| `access` | 60 min | Bearer en cada llamada a `/api/v1/*` |
| `refresh` | 7 días | Sólo contra `/auth/refresh` para emitir un nuevo par |

Claims:

```
{
  "sub": "<user_id>",
  "role": "admin|operator|viewer",
  "type": "access|refresh",
  "iat": ..., "exp": ..., "iss": "VanguardOps",
  "jti": "<uuid hex>"
}
```

`jti` garantiza tokens únicos aunque se emitan en el mismo segundo, y abre la puerta a una tabla de revocación si llega a hacer falta.

Passwords se almacenan con **bcrypt** (passlib). El `decode_token` exige `expected_type` para impedir confundir un refresh con un access.

## Consecuencias

* ✅ Cero infraestructura adicional: `SECRET_KEY` y listo.
* ✅ Compatible con la "Authorize" button de Swagger UI.
* ✅ `access` corto + `refresh` largo limita el blast radius de un token comprometido.
* ⚠️ La revocación inmediata requiere persistir `jti`s revocados. Aceptado como follow-up.
* ⚠️ Si el `SECRET_KEY` se filtra todos los tokens son inválidables; rotación documentada en `docs/security.md` (TODO).
