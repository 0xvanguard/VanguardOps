# ADR-006: Hardening del Dockerfile y aislamiento de red en Compose

* Estado: Aceptado
* Fecha: 2026-05-23

## Contexto

El primer `docker-compose.yml` exponía PostgreSQL en `5432` y Redis en `6379` directamente al host. Eso significa que cualquier servicio en el host (incluido un atacante en una LAN compartida) podía:

* abrir conexiones al broker de Celery sin pasar por la API,
* leer/escribir en la base de datos sin autenticación de aplicación,
* enumerar versiones explotables de PostgreSQL/Redis.

Además, el `Dockerfile` original era una sola imagen con compiladores en runtime, ejecutaba como `root`, y no incluía un PID 1 que reenviara `SIGTERM`, dejando procesos huérfanos cuando el orquestador reiniciaba el contenedor.

## Decisión

### Dockerfile (multi-stage + no-root + tini)

```dockerfile
# Stage 1: builder con build-essential, libpq-dev, instala deps en /opt/venv
FROM python:3.12-slim AS builder ...

# Stage 2: runtime sin compiladores, usuario vanguard:1001, tini como PID 1
FROM python:3.12-slim AS runtime
RUN apt-get install -y libpq5 curl tini && \
    useradd --system --uid 1001 vanguard
COPY --from=builder /opt/venv /opt/venv
USER vanguard
HEALTHCHECK CMD curl -fs http://127.0.0.1:8000/livez || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", ...]
```

Beneficios:

* Imagen final ≈ 200 MB sin compiladores, sin pip cache, sin source de build deps.
* `tini` como PID 1 reenvía señales: `docker stop` propaga `SIGTERM` a uvicorn / celery, que pueden cerrar conexiones limpiamente.
* Usuario no-root + `read_only: true` + `tmpfs: /tmp` mitigan escapes de filesystem.
* `cap_drop: [ALL]` y `security_opt: [no-new-privileges:true]` siguen el principio de mínimo privilegio.

### Aislamiento de red en Compose

* PostgreSQL y Redis **no** mapean puertos al host por defecto. Quedan en una red interna `internal` solo accesible para los demás servicios.
* La API es el **único** servicio expuesto públicamente (`8000:8000`).
* Para depuración local existe el perfil opt-in `dev-tools`, que levanta un `socat` que reenvía 5432/6379 desde el host. **Nunca** debe activarse en producción.
* `pgAdmin` y `Flower` viven detrás de sus propios perfiles (`admin`, `monitoring`).

```bash
docker compose up -d                            # API expuesta, datastores aislados
docker compose --profile dev-tools up -d        # + 5432/6379 expuestos en localhost
```

## Consecuencias

* ✅ Superficie de ataque mínima: un escaneo de puertos en el host solo encuentra `:8000`.
* ✅ Cierre limpio de conexiones DB y workers ante `docker stop`/Kubernetes preStop hook.
* ✅ Cumple recomendaciones del [Docker Bench for Security](https://github.com/docker/docker-bench-security) sobre runtime non-root, read-only fs y caps droppeados.
* ⚠️ Requiere ejecutar `docker compose --profile dev-tools up` cuando un dev quiere conectarse con `psql`/`redis-cli` desde el host.
* ⚠️ `read_only: true` exige que las apps no escriban en `/`. Los logs van a stdout (structlog) y `/tmp` queda como tmpfs para artefactos efímeros.
