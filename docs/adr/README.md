# Architecture Decision Records (ADRs)

Este directorio guarda decisiones de arquitectura significativas. Cada ADR documenta el **contexto**, las **opciones consideradas**, la **decisión tomada** y sus **consecuencias** (positivas y negativas).

Formato basado en el [template de Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

## Índice

| # | Estado | Título |
|---|--------|--------|
| [001](001-arquitectura-en-capas.md) | Aceptado | Arquitectura en capas (api/services/crud/models) |
| [002](002-errores-rfc-7807.md) | Aceptado | Errores HTTP en formato RFC 7807 |
| [003](003-autenticacion-jwt.md) | Aceptado | Autenticación basada en JWT con roles |
| [004](004-alembic-migraciones.md) | Aceptado | Migraciones gestionadas con Alembic (sin `create_all` en runtime) |
| [005](005-celery-claim-atomico.md) | Aceptado | Bloqueo pesimista (`FOR UPDATE SKIP LOCKED`) para workflows |
| [006](006-docker-hardening-y-aislamiento.md) | Aceptado | Hardening Docker y aislamiento de red en Compose |
| [007](007-jwt-blacklist-fail-closed.md) | Aceptado | JWT blacklist en Redis con política fail-closed |
| [008](008-rate-limit-and-ip-banning.md) | Aceptado | Rate limiting (sliding window) + banlist dinámica de IPs |

## Cómo añadir un ADR

1. Copia [`_template.md`](_template.md) con el siguiente número correlativo.
2. Empieza el documento en estado **Propuesto**.
3. Discútelo en el PR. Cuando se mergea, cámbialo a **Aceptado**.
4. Si una decisión posterior anula esta, márcala como **Reemplazado por ADR-XXX** y deja la nueva en su lugar.
