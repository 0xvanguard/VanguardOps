# ADR-007: Política de fallo del JWT blacklist (fail-closed con red operacional)

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

El esquema de autenticación de VanguardOps (ver [ADR-003](003-autenticacion-jwt.md)) emite JWTs con `exp` y `jti`. Mientras un token tenga firma válida y no esté caducado, **es aceptado**. Esto significa que:

* No hay forma de hacer "logout" antes de `exp`.
* Si un token se compromete, el blast radius es de hasta `ACCESS_TOKEN_EXPIRE_MINUTES` (60 min por default).
* La rotación de `SECRET_KEY` invalida *todos* los tokens — útil ante una brecha global, inutilizable para revocar uno solo.

El fix estándar es una **lista negra de `jti`s revocados**, consultada en cada `decode_token`. La pregunta interesante no es "¿la implementamos?" — sí — sino **qué hace `decode_token` cuando la lista negra está caída**.

## Decisión

Implementamos una lista negra **respaldada por Redis (DB lógica `/2`)** con TTL dinámico (`ttl = max(1, exp − now)`). Cuando la consulta a Redis falla, el comportamiento por default es **fail-closed**: la API responde `401 invalid_credentials` con un mensaje genérico.

```
                                        success → continue
                                       /
decode_token ─► verify signature ─► check jti in Redis ─► allow / reject
                                       \
                                        Redis error → 401 (closed)
                                                    └─ or honor token (open, opt-in)
```

### Por qué fail-closed por default

| Modo        | Caída silenciosa de Redis | Caída ruidosa de Redis | Token comprometido + DoS a Redis |
|-------------|---------------------------|------------------------|----------------------------------|
| **Closed**  | Imposible: 401s loud      | 401s loud              | Atacante también queda fuera     |
| Open        | Tokens revocados se honran sin alarma | API up, riesgo silencioso | Atacante usa token hasta `exp`   |

Un fallo silencioso de seguridad es siempre peor que un fallo ruidoso de disponibilidad. El primero se descubre en una auditoría meses después; el segundo se descubre en 30 segundos por el pager.

### Mitigaciones que neutralizan el costo de uptime

1. **`/readyz` chequea Redis `/2` específicamente.** Si la blacklist está caída, el pod se reporta `not_ready` y el orquestador (k8s/Compose) lo saca del LB. Otros pods sanos siguen sirviendo. Desde la óptica del usuario, fail-closed se *siente* como fail-open: nunca ve el 401 de "Redis down".

2. **Producción exige Redis HA para la DB `/2`.** Mínimo Sentinel (3 nodos) o Redis Cluster, o un servicio gestionado equivalente (ElastiCache, MemoryDB, Upstash, Redis Enterprise Cloud). Una instancia single-node solo es aceptable en `staging` o entornos efímeros.

3. **Escape hatch sin redeploy.** La variable `JWT_BLACKLIST_ON_REDIS_FAILURE` (`closed` | `open`, default `closed`) se puede flipear en segundos vía `kubectl set env` o `docker compose up` cuando una catástrofe real (region down) prioriza uptime sobre revocación inmediata. Cada request servido en modo `open` incrementa la métrica `auth_blacklist_fail_open_total`, que mantiene el dashboard rojo hasta que ops la revierta explícitamente.

4. **Telemetría fuerte.** Tres counters Prometheus:
   * `auth_blacklist_redis_errors_total{operation}` — un tick por error.
   * `auth_blacklist_fail_open_total` — ticks solo en modo degradado.
   * `auth_blacklist_revocations_total` — éxitos de revocación, útil para dashboards de seguridad.

### Por qué Redis DB `/2` y no la `/0`

Segregar las DBs lógicas:

| DB    | Uso                              | Riesgo de FLUSHDB |
|-------|----------------------------------|-------------------|
| `/0`  | Celery broker (colas de trabajo) | Operación rutinaria al limpiar colas tras un deploy |
| `/1`  | Celery result backend            | Limpieza periódica de resultados |
| `/2`  | **Blacklist JWT**                | **Nunca**: invalidaría todas las revocaciones activas |

Un dev haciendo `redis-cli FLUSHDB` en la `/0` tras un cambio de tareas Celery **no debe** poder, accidentalmente, anular el logout de todos los usuarios. La segregación lo hace estructuralmente imposible.

### Por qué TTL dinámico

`SET jwt:blacklist:{jti} 1 EX {exp - now}`

* **Memoria acotada:** la blacklist crece con tokens *outstanding*, no con históricos. Un atacante no puede llenarla con revocaciones eternas.
* **Coincide con la criptografía:** Redis evicciona la entrada justo cuando el JWT habría caducado de todos modos. Cero ruido temporal.
* **Sin job de limpieza:** delegamos GC al motor de Redis. Cero código de housekeeping.

Floor de `1` segundo: Redis rechaza `EX=0`, así que tokens ya caducados al momento de revocarlos reciben un placeholder de 1s. No introduce vulnerabilidad porque el JWT también está caducado y el chequeo de `exp` lo rechaza primero.

### Orden de validación en `decode_token`

```
1. jwt.decode (firma + decode)   ~10–100 µs   local, CPU
2. expected_type check            free        en memoria
3. blacklist Redis EXISTS         ~0.5–2 ms   red local
4. (downstream) DB user lookup    ~5–20 ms    PostgreSQL
```

La firma criptográfica se valida **primero** porque (a) es más barata que Redis y (b) sin esto el `jti` es untrusted — un atacante podría enviarnos `jti`s arbitrarios y nos forzaría a martillar Redis con consultas inútiles. Crypto first es la única opción correcta.

## Consecuencias

### Aceptadas
* Dependencia adicional de Redis HA en producción.
* ~0.5–2 ms de latencia adicional por request autenticado (lectura `EXISTS`).
* La caída prolongada de Redis `/2` es un incidente operativo (alarma, paging) en lugar de un riesgo de seguridad silencioso.

### Rechazadas (de fail-open puro)
* Ventana de aceptación silenciosa de tokens revocados durante un outage.
* Imposibilidad de auditoría firme post-incidente ("¿este token revocado se aceptó cuando Redis cayó?").
* Combinable trivialmente con DoS dirigido a Redis para extender la vida útil de un token comprometido.

### Trade-off operativo
La política está *configurada en tiempo de ejecución*, no en código. Un equipo con un compromiso de uptime extremo (SLA 99.99%+) sin tolerancia a 401s breves puede operar permanentemente en `open` con observabilidad estricta — pero la decisión queda visible en una variable de entorno, auditable, y reversible en segundos.
