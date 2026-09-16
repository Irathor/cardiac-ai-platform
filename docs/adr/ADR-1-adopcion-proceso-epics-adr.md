# ADR-1: Adopción del proceso Epics/ADR sobre un proyecto existente

## Estado
Aceptada

## Contexto
El proyecto ha documentado su avance hasta ahora como un changelog de fases en el
`README.md` (Fase 1 a Fase 8, ver también `docs/phases.md`), todas ellas verificadas con
tests reales contra SQLite en memoria y contra Postgres/MinIO/MLflow reales dentro del
stack completo de Docker Compose. Este formato ha funcionado bien para documentar trabajo
ya cerrado, pero el usuario quiere ampliar el proyecto hacia un roadmap de MLOps más
amplio (explicabilidad real sobre modelos de imagen, servir modelos reales desde la API de
inferencia, un Model Registry más maduro, monitoring, detección de drift, CI/CD ampliado y,
eventualmente, despliegue cloud con Infrastructure as Code) y ha pedido adoptar el proceso
de Epics y ADR que usa su equipo (Shepard/Liara/Tali/Miranda/EDI/Garrus/Mordin) para
organizar ese trabajo nuevo, en vez de seguir apilando fases en el README.

Se valoraron dos opciones:
1. Reescribir/migrar retroactivamente el changelog de fases existente a Epics, para que todo
   el repositorio hable un único formato de documentación desde el principio del proyecto.
2. Adoptar Epics/ADR solo para el trabajo nuevo a partir de este punto, dejando el changelog
   de fases existente tal cual está.

## Decisión
Se adopta `docs/epics/` y `docs/adr/` para todo el trabajo nuevo del proyecto a partir de
ahora. El changelog de fases existente en el `README.md` (Fases 1-8) **no se reescribe ni se
migra retroactivamente** a Epics — queda como está, documentando el trabajo ya cerrado y
verificado. Las fases futuras del roadmap de MLOps se documentan como Epics numeradas desde
EPIC-1, siguiendo la plantilla estándar del equipo.

Se descarta la opción de migración retroactiva: no aporta valor real (el trabajo de las
Fases 1-8 ya está cerrado, verificado y descrito con un nivel de detalle que la plantilla de
Epic no mejora) y tiene el coste de reescribir documentación estable sin necesidad.

## Consecuencias
- A partir de este ADR, el repositorio convive con **dos formatos de documentación de
  progreso simultáneos y deliberados**, no accidentales: el `README.md` (con su sección
  "Project status" y `docs/phases.md`) sigue siendo la fuente de verdad de las Fases 1-8 ya
  cerradas; `docs/epics/` y `docs/adr/` son la fuente de verdad de todo lo que se decida y
  construya de aquí en adelante.
- El `README.md` incorpora una sección corta ("Ver también") que apunta a `docs/epics/` y
  `docs/adr/`, para que quien lo lea entienda que el roadmap nuevo vive ahí y no se
  interprete la ausencia de nuevas "Fases" como que el proyecto se detuvo.
- Cualquier decisión técnica relevante tomada de aquí en adelante (elección de tecnología,
  contratos entre servicios, cambios de arquitectura) se documenta con un ADR nuevo, no como
  una entrada más de changelog en el README.
