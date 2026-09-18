# ADR-8: Servicio puente en el host para disparar entrenamiento real de U-Net/CNN3D en GPU

## Estado
Aceptada

## Contexto
[EPIC-17: Selección de modelo al reentrenamiento + panel de validación completo](
../epics/EPIC-17-seleccion-modelo-reentrenamiento-panel-validacion.md) necesita que el worker
Celery (que corre dentro de Docker) pueda disparar el entrenamiento real de U-Net 2D y CNN3D,
que hoy solo se ejecuta a mano con `ml/.venv-dl` sobre una GPU real del host. El worker no tiene
acceso a GPU: es un contenedor Docker Desktop en Windows sin passthrough de GPU configurado.

Opciones valoradas:
1. **GPU passthrough en Docker** (WSL2 + `--gpus`, o Docker Desktop con soporte CUDA). Descartado
   para esta máquina/entorno: en pruebas previas de esta sesión resultó frágil (dependiente de
   versión de driver, de la configuración exacta de WSL2 y de Docker Deskop, con fallos
   intermitentes difíciles de diagnosticar de forma reproducible) frente al beneficio de tener
   todo el entrenamiento dentro de un único contenedor. Se descarta como mecanismo de esta
   iteración, no de forma permanente — si el entorno de despliegue cambia (p. ej. GPU en un host
   Linux dedicado en vez de Windows+Docker Desktop) puede revisarse.
2. **Dejar U-Net/CNN3D fuera del flujo de la aplicación**, manteniéndolos como scripts sueltos
   ejecutados a mano. Descartado: contradice directamente el pedido del usuario de poder
   elegir y disparar cualquiera de los tres modelos desde el panel de administración.
3. **Servicio puente HTTP mínimo en el host** (`ml/scripts/training_runner_service.py`), que el
   worker Celery alcanza vía `http://host.docker.internal:8800` (resuelto automáticamente por
   Docker Desktop en Windows, sin configuración de red adicional) y que ejecuta el script de
   entrenamiento real como subproceso dentro de `.venv-dl`, sobre GPU real. Elegida.

## Decisión
Se implementa `ml/scripts/training_runner_service.py`: un servidor HTTP mínimo (`http.server` de
la librería estándar de Python, sin dependencias nuevas), con una cola en memoria (sin
persistencia — si se reinicia, el job en curso falla limpiamente y se puede reintentar), que
expone:
- `POST /jobs {"model_type": "UNET_SEGMENTATION"|"CNN3D_CLASSIFICATION"}` — lanza el script de
  entrenamiento correspondiente como subprocess dentro de `.venv-dl/Scripts/python.exe`.
- `GET /jobs/{id}` — estado (`QUEUED|RUNNING|COMPLETED|FAILED`), cola de log y ruta de
  resultado.

El worker Celery, dentro de `execute_dl_training`, hace `POST` y luego `poll` con timeout
(evitando quedarse colgado indefinidamente si el runner no responde o el job nunca termina) y,
al completar, lee los pesos (`.pt`) y el JSON de métricas directamente desde `/data`
(bind-mount compartido entre host y contenedores, ver `docker-compose.yml`), sin transferir
archivos por HTTP.

Es un **prerequisito manual** documentado en `docs/dl-training-runner.md`
(`ml/.venv-dl/Scripts/python ml/scripts/training_runner_service.py`), nunca arrancado
automáticamente por Celery ni por `docker compose up` — si no está corriendo, el training run
falla con un mensaje claro en vez de quedarse en `RUNNING` para siempre.

## Consecuencias
- **Ventaja**: U-Net y CNN3D quedan disparables desde el panel de administración usando GPU
  real, sin la fragilidad observada del GPU passthrough en Docker en esta máquina, y sin
  reescribir los scripts de entrenamiento que ya funcionan.
- **Desventaja/deuda asumida**: el flujo de entrenamiento DL depende de un proceso manual fuera
  de `docker compose up` — no es "un solo comando" para todo el stack. Documentado
  explícitamente para que no se confunda con un fallo silencioso.
- **Superficie de seguridad**: el servicio puente hace `bind` explícito a `127.0.0.1` (no
  `0.0.0.0`), sin autenticación propia — alcanzable desde los contenedores solo porque Docker
  Desktop en Windows resuelve `host.docker.internal` hacia servicios del host, no porque el
  puerto esté expuesto a la red. Aceptado en el contexto actual (máquina de desarrollo/operador
  único, mismo criterio ya usado en otras decisiones de este proyecto para infraestructura no
  expuesta públicamente); si el proyecto se despliega en un host compartido, multi-operador, o
  fuera de Docker Desktop para Windows (donde `host.docker.internal` puede comportarse distinto),
  esto debería revisarse (autenticación mínima entre worker y runner).
- **Impacto en otros módulos**: ninguno sobre el flujo de nearest-centroid (sigue síncrono
  dentro del worker, sin pasar por el runner). `app/core/config.py` añade
  `training_runner_url`/`data_root`; `docker-compose.yml` añade el bind mount `./data:/data` a
  `backend` y `worker`.
