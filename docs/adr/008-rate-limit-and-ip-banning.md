# ADR-008: Rate limiting con sliding-window + banlist dinámica de IPs

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

El cierre de Sprint D dejó la autenticación blindada con JWT + blacklist (ADR-007), pero los endpoints de auth seguían expuestos al **bombardeo**: un atacante podía probar miles de credenciales por minuto contra `/auth/login`, o ejecutar un escáner de vulnerabilidades como `dirb` / `gobuster` para mapear rutas internas. Sin un control de tráfico previo al enrutador de FastAPI, cada intento gastaba CPU verificando bcrypt y consultando PostgreSQL.

`slowapi`, que se había añadido en Sprint C, nunca llegó a aplicarse a ninguna ruta (`default_limits=[]` en código real). Se eliminó en este mismo PR a favor de un middleware en casa que cumple los dos requisitos:

* **Rate limiting** robusto frente a ráfagas en el límite de la ventana.
* **Banning dinámico** de IPs que muestran patrón de abuso (auth fails repetidos o escaneo masivo de 404s).

## Decisión

### Algoritmo: Sliding Window Log

Tres opciones consideradas:

| Algoritmo | Pro | Contra |
|-----------|-----|--------|
| Fixed window | Simple, una cuenta por ventana. | Permite un burst de `2 × limit` cruzando el boundary entre ventanas. |
| Token bucket | Suaviza ráfagas, fácil de razonar para tráfico continuo. | Aproximado en los límites; difícil garantizar "máximo N en N segundos" exacto. |
| **Sliding window log** ✅ | Cuenta exacta de "requests en los últimos N segundos". | `O(N)` por entrada por ventana, pero acotado por `limit`. |

Para endpoints de seguridad crítica (`/auth/login`, `/auth/register`) la precisión gana sobre el coste de memoria. Implementación con un Redis ZSET por `(scope, identificador)`:

```python
ZREMRANGEBYSCORE key 0 (now - window)   # purga miembros viejos
ZCARD key                                 # cuenta actual
if count >= limit: REJECT
ZADD key {uuid}: now                      # registra esta request
EXPIRE key (window + 60)                  # safety TTL
```

Una pequeña race window existe entre `ZCARD` y `ZADD` (no usamos Lua scripts para mantener compatibilidad con el `FakeRedis` de tests). El peor caso es `limit + N_concurrent` aceptados en lugar de exactamente `limit` — aceptable para mitigación de abuso.

### Storage: Redis DB lógica `/3`, segregada

| DB    | Uso                              | Riesgo de FLUSHDB |
|-------|----------------------------------|-------------------|
| `/0`  | Celery broker                    | Operación rutinaria al limpiar colas. |
| `/1`  | Celery result backend            | Limpieza periódica de resultados. |
| `/2`  | Blacklist JWT (ADR-007)          | **Nunca**: invalidaría todas las revocaciones activas. |
| `/3`  | **Rate limiter + banlist** ✅    | **Nunca**: liberaría IPs banneadas y reseteo de cuentas. |

La segregación es estructural, no convención: si un dev hace `FLUSHDB` en `/0` después de un cambio de tareas Celery, **no puede**, accidentalmente, liberar IPs banneadas o resetear las ventanas de rate limit.

### Banlist dinámico con escalación

Dos contadores por IP, ambos con TTL deslizante que se refresca con cada incremento:

* `ban:fails:{ip}` — cuenta fallos de autenticación (401 desde `/auth/login*` o `/auth/refresh`). Threshold: **10 fallos en 5 minutos**.
* `ban:404:{ip}` — cuenta respuestas 404 (indicador de escaneo). Threshold: **20 404s en 1 minuto**.

Cuando cualquier umbral se cruza, la IP entra en `ban:active:{ip}` con TTL = duración del ban actual. Cada ban incrementa `ban:count:{ip}` (ladder counter, TTL 24h):

| Ban # | Duración |
|-------|----------|
| 1     | 15 minutos |
| 2     | 1 hora |
| 3+    | 24 horas (capado) |

El `ban:count:{ip}` tiene TTL de 24h. Un ciudadano cuya IP era de un offender previo recupera el ladder ligero después de 24h sin incidentes.

Decisión deliberada: **`is_banned` falla abierto** en outages de Redis. La banlist es mitigación de abuso, no boundary de seguridad — el fail-closed estricto está en la blacklist JWT (ADR-007). Si Redis `/3` cae, los usuarios legítimos no quedan bloqueados; el atacante simplemente vuelve a poder bombardear hasta que Redis vuelva, momento en el cual se vuelve a banear.

### Decisión de proxy: TRUST_PROXY explícito

Leer `X-Forwarded-For` ciegamente es un vector clásico de **IP spoofing**: cualquier cliente puede enviar `X-Forwarded-For: 127.0.0.1` y eludir las restricciones por IP. La extracción de IP del cliente solo honra `X-Forwarded-For` cuando la variable `TRUST_PROXY=True` está activa, lo cual debe configurarse explícitamente cuando hay un balanceador de confianza (ALB, nginx con `set_real_ip_from`) delante.

Se toma el **primer hop** del header (no el último), siguiendo la convención `client, proxy1, proxy2, ...`.

### Whitelist por CIDR

`RATE_LIMIT_WHITELIST_CIDRS` (variable de entorno, lista CSV) permite excluir totalmente del rate limiter y la banlist a redes de confianza:

* Oficinas que pueden generar ráfagas legítimas.
* Sistemas de monitoring que polean `/livez` cientos de veces por minuto (aunque las health rutas ya están exentas por path).
* Scanner internos de seguridad que ejecutamos a propósito.

Implementado con `ipaddress.ip_network` para soportar IPv4 e IPv6, con `strict=False` para tolerar máscaras de bits distintas a la canónica.

## Consecuencias

### Aceptadas

* Latencia adicional ~0.5–2ms por request autenticado (1 ZSET op + 1 EXISTS para banlist).
* Memoria proporcional a tokens outstanding × limit, acotada por `EXPIRE` automático.
* Race window microscópica en sliding-window que puede dejar pasar `N_concurrent − 1` extras en el límite. No relevante para la magnitud de abuso que estamos previniendo.

### Rechazadas

* **Token bucket**: aproximado en boundary, no apto para `/auth/login`.
* **Fixed window**: vector de doble burst en el cambio de bucket.
* **Lua script en lugar de pipeline secuencial**: añade dependencia de Lua en testing infrastructure (`FakeRedis` no implementa EVAL). El gain de atomicidad estricta no compensa la complejidad para tests.
* **Reusar Redis `/0`** o `/2`: rompería la segregación que ADR-007 estableció.
* **slowapi**: feature equivalente con extras pero menor control sobre el algoritmo y peor integración con Problem+JSON.

### Trade-off operativo

`JWT_BLACKLIST_ON_REDIS_FAILURE` (ADR-007) es fail-closed por default. La banlist es **fail-open** porque su falta deja la API funcional pero abre la ventana de bombardeo. Si en el futuro decidimos endurecer la banlist a fail-closed, el patrón a seguir es el mismo de ADR-007: variable de entorno con escape hatch operacional + métrica Prometheus que mantiene el dashboard rojo en modo degradado.

## Métricas Prometheus expuestas

| Métrica | Tipo | Labels | Significado |
|---------|------|--------|-------------|
| `rate_limit_hits_total` | Counter | `scope`, `outcome` (`allowed`/`denied`) | Ticks por evaluación de rate limit. |
| `rate_limit_redis_errors_total` | Counter | — | Fallos contra Redis `/3` desde el limiter. |
| `ip_bans_activated_total` | Counter | `reason` | Bans nuevos activados. |
| `ip_ban_blocked_requests_total` | Counter | `reason` | Requests rechazadas por estar la IP banneada. |
| `ip_banlist_redis_errors_total` | Counter | `operation` | Fallos contra Redis `/3` desde la banlist. |

Dashboards recomendados:

* "Auth abuse pressure": `rate(rate_limit_hits_total{scope="auth_login",outcome="denied"}[5m])` por origen.
* "Active bans": `sum(ip_bans_activated_total) by (reason)`.
* "Scanner activity": `rate(ip_bans_activated_total{reason="scan_attempt"}[5m])`.
