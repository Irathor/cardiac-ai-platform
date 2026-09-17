# EPIC-5: CI/CD ampliado — escaneo de dependencias + build/push de imágenes

## Historia de usuario
Como equipo, quiero que el pipeline de CI escanee dependencias vulnerables y construya/
publique imágenes Docker, para tener una base lista de cara a cualquier despliegue cloud
futuro y detectar vulnerabilidades conocidas de forma temprana.

## Tipo
Normal

## Bloqueada por
Ninguna

## Criterios de aceptación
- [x] El pipeline de CI ejecuta `pip-audit` sobre las dependencias de `backend/` y `ml/`,
      como gate real (falla el job si hay vulnerabilidades conocidas), no solo informativo.
- [x] El pipeline de CI ejecuta `npm audit --audit-level=high` sobre las dependencias de
      `frontend/`.
- [x] El pipeline construye imágenes Docker en cada push/PR y las publica (push) a **GHCR**
      (GitHub Container Registry — elegido por integrar `GITHUB_TOKEN` automático sin
      secretos nuevos, no es decisión grande per el propio texto de esta Epic) solo en push a
      `master`, nunca desde una PR de rama externa.

Al activar el gate real de `pip-audit` se descubrieron 70 vulnerabilidades ya presentes en el
proyecto (`mlflow` 2.22.5 muy desactualizado, `starlette`/`pyarrow`/`pytest`). Consultado el
usuario explícitamente (trade-off de seguridad real, no decidible en autonomía): se decidió
actualizar `mlflow` a la última versión estable en vez de solo silenciar el gate — ver
"Verificación" abajo para el detalle completo del upgrade y lo que rompió/arregló.

## Alcance
Configuración de CI (workflow existente), `Dockerfile`s de `backend/` y `frontend/`.

## Fuera de alcance
Despliegue automático a ningún entorno real todavía (eso es EPIC-8).

## Verificación
- Workflow corregido de paso: el trigger `on.push.branches` apuntaba a `main`, la rama real
  del repo es `master` — nunca había disparado en push hasta este cierre.
- Actualización de dependencias real (verificada contra PyPI, no de memoria): `mlflow`
  `2.17→3.16.1`, `starlette` `0.47.2→1.6.0`, `fastapi` `0.118→0.141` (necesario para permitir
  el starlette nuevo), `pytest`/`pytest-asyncio` a sus últimas versiones estables. `pyarrow`
  (transitiva de mlflow) queda resuelta a `25.0.1` sin conflicto con sqlalchemy/alembic.
  Imagen del servidor MLflow (`infrastructure/mlflow/Dockerfile`) subida también a `3.16.1`
  para evitar drift cliente/servidor.
- `ecdsa` (PYSEC-2026-1325, ataque de timing "Minerva", transitiva de `python-jose`) se
  ignora explícitamente con `--ignore-vuln` y motivo documentado en el propio workflow: no
  existe versión parcheada en PyPI, y `security-review` confirmó que este proyecto firma JWT
  con HS256 (simétrico), nunca ejercita la ruta ECDSA de `python-jose` — la CVE no es
  explotable aquí aunque la dependencia esté presente.
- Rotura real detectada y arreglada por el upgrade de mlflow: `mlflow.register_model` con
  URIs `runs:/<run_id>/<artifact_path>` cambió de comportamiento en mlflow 3.x (exige un
  "Logged Model"/`MLmodel`, este proyecto registra artefactos crudos). Arreglado con
  `training_service.py::_register_raw_artifact_model_version`, que replica el patrón oficial
  de mlflow para este caso. `transition_model_version_stage` (EPIC-4) sigue funcionando tal
  cual, deprecado pero no eliminado — deuda técnica anotada en `docs/BACKLOG.md`.
- `backend`: 124/124 tests en verde, `ruff check` limpio, `pip-audit --local` limpio (solo
  `ecdsa` ignorada explícitamente) — todo re-ejecutado de forma independiente por el
  orquestador, no solo aceptado del informe de Tali.
- `ml`: 31/31 en `.venv` (CPU) + 166/166 en `.venv-dl` (GPU real) en verde, `ruff check`
  limpio en ambos entornos — re-ejecutado de forma independiente.
- `frontend`: `npm audit --audit-level=high` limpio (2 vulnerabilidades moderate existentes
  en `vitest`/`@vitest/mocker`, por debajo del umbral del gate).
- Verificación end-to-end real contra un servidor MLflow 3.16.1 containerizado (Postgres+
  MinIO reales vía `docker compose`): registro de modelo y transición de stage funcionaron
  correctamente.
- `security-review` (skill del orquestador) ejecutado sobre el diff completo: sin hallazgos
  — `GITHUB_TOKEN`/`packages:write` acotado al job `build-and-push`, doble condición
  (`login` + `push:`) sobre push-a-master real, sin interpolación insegura de contexto
  no confiable de GitHub Actions, sin construcción insegura de rutas en el nuevo helper de
  registro de MLflow.

## Estado
Completada
