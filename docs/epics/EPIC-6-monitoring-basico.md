# EPIC-6: Monitoring básico y métricas de inferencia servida

## Historia de usuario
Como equipo, quiero monitorizar la inferencia real servida (latencia, volumen, errores),
para tener visibilidad operativa mínima sobre el sistema en producción/demo.

## Tipo
Normal

## Bloqueada por
EPIC-2 (Servir los modelos reales (U-Net/CNN3D) desde la API de inferencia) — monitorizar
algo que todavía no se sirve no aporta señal real.

## Criterios de aceptación
- [ ] Existe como mínimo un endpoint `/metrics` propio con métricas de inferencia servida.
- [ ] Queda decidido si se añade Prometheus+Grafana como contenedor adicional al stack, o si
      el endpoint `/metrics` propio es suficiente para esta fase.

## Alcance
Backend (nuevo endpoint de métricas), posible contenedor adicional en `docker-compose.yml`.

## Fuera de alcance
Alertas, trazas distribuidas.

## Nota
Requiere decisión previa del usuario sobre el stack de monitoring (endpoint propio vs.
Prometheus+Grafana) antes de poder implementarse — ver Shepard/Liara cuando toque.

## Estado
Propuesta
