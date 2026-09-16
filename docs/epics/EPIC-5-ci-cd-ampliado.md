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
- [ ] El pipeline de CI ejecuta `pip-audit` sobre las dependencias de `backend/` y `ml/`.
- [ ] El pipeline de CI ejecuta `npm audit` sobre las dependencias de `frontend/`.
- [ ] El pipeline construye y publica (push) imágenes Docker a un registro (Docker Hub o
      GHCR — la elección concreta no es una decisión grande, se documenta si amerita ADR).

## Alcance
Configuración de CI (workflow existente), `Dockerfile`s de `backend/` y `frontend/`.

## Fuera de alcance
Despliegue automático a ningún entorno real todavía (eso es EPIC-8).

## Estado
Propuesta
