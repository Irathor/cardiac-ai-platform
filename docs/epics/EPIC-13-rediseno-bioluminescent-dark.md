# EPIC-13: Rediseño visual hacia la dirección "Bioluminescent Dark"

## Historia de usuario
Como usuario que va a mostrar esta plataforma como pieza insignia de su
portfolio de AI/ML Engineering, quiero evolucionar el tema oscuro "AI-Ops"
de EPIC-10 hacia una dirección de arte "Bioluminescent Dark" (paleta
teal-negro profundo con acento verde bioluminiscente, tipografía display
Bricolage Grotesque + cuerpo IBM Plex Sans) para diferenciar visualmente el
producto de un dashboard oscuro genérico, manteniendo la misma disciplina
de jerarquía y codificación por dominio que ya validó EPIC-10.

## Tipo
Normal

## Bloqueada por
EPIC-10 (Rediseño visual del frontend hacia un tema oscuro "AI-Ops"
moderno y cercano) — esta Epic reemplaza la paleta y tipografía que dejó
EPIC-10 sobre la misma arquitectura de tokens (`quietSurface()`/
`heroSurface()`), no la reconstruye desde cero.

## Criterios de aceptación

### Tokens y tipografía (`frontend/src/theme.ts`)
- [x] `tokens` se migra a la paleta "Bioluminescent Dark": `bgVoid` =
      `#071a1a`, `surface` = `#0f2b28`, acento primario (dominio
      clínico/paciente, mismo rol que hoy `cyan`) = `#34f5c1`, acento
      secundario (dominio MLOps/modelo, mismo rol que hoy `violet`) =
      `#7c6ff2`, `textPrimary` = `#eafaf6`, `textSecondary` = `#8fb8ae`,
      `line` = `#163634`. Se conservan las claves derivadas que el resto
      del código consume (`surfaceRaised`, variantes `*Dark`) recalculadas
      sobre los hexes nuevos, no dejadas con los valores viejos.
- [x] `quietSurface()` y `heroSurface(accent)` siguen existiendo con
      exactamente el mismo contrato/firma que en EPIC-10 (mismos
      parámetros, mismo tipo `Accent`, misma diferencia quiet=plano/
      hero=elevado+glow direccional) — solo cambian los hexes que
      consumen internamente. Ningún call site de `quietSurface()`/
      `heroSurface()` en el resto del código necesita cambiar su forma de
      llamada.
- [x] `typography.fontFamily` (cuerpo/UI) pasa a IBM Plex Sans (con
      fallback a system sans-serif razonable). `h3`/`h4` (hoy en Space
      Grotesk) pasan a Bricolage Grotesque, con el mismo criterio que
      EPIC-10: reservado a titulares/métricas destacadas, nunca mezclado
      con la tipografía de cuerpo en el mismo texto. Ambas fuentes se
      cargan como variable font desde Google Fonts (peso/anchura
      ajustables por contexto sin cargar una segunda familia adicional
      para titular vs. métrica).
- [x] `chartColors`, `categoricalChartColors`, `chartTooltipStyle`,
      `heatCellColor` y el resto de exports derivados de `tokens` quedan
      recalculados sobre la paleta nueva (no quedan referencias sueltas a
      los hexes de EPIC-10 en `theme.ts`).
- [x] El comentario de cabecera de `theme.ts` se actualiza para describir
      la dirección "Bioluminescent Dark" (paleta, tipografía, metáfora
      "señal viva") en vez de dejar la documentación de EPIC-10 sin
      actualizar.

### Aplicación real a las superficies
- [x] El rediseño se aplica de verdad (no solo vía herencia del tema) a
      las mismas superficies que tocó EPIC-10: `SiteHeader.tsx`,
      `DashboardPage.tsx`, `ImagingViewerPage.tsx`,
      `ModelTrainingPage.tsx` y sus tabs (`ClassificationTab`,
      `CalibrationTab`, `ValidationTab`), `LoginCard.tsx`,
      `ResearchDisclaimerBanner.tsx`. Para cada archivo que no requiera
      cambios propios (por heredar 100% del tema/tokens compartidos), se
      verifica por inspección directa y se deja constatado en el resumen
      de cierre, igual que hizo EPIC-10.
- [x] La metáfora "señal viva" se aplica con propósito narrativo (trazas/
      pulsos que evocan actividad biológica real allí donde ya existía
      motion de EPIC-10 — p. ej. el pulso de estado en vivo — o donde
      tenga sentido de dominio), no como glow decorativo repetido sin
      motivo. Se mantiene la jerarquía quiet/hero de EPIC-10 (un único
      hero por pantalla) sin reinventarla.
- [x] `NiftiViewer.tsx` se revisa visualmente con la paleta nueva y se
      confirma legibilidad real: el acento verde bioluminiscente cerca de
      imágenes médicas en escala de grises no compromete la lectura de la
      imagen ni introduce ambigüedad de color con hallazgos clínicos.
      Contraste verificado con capturas reales, no asumido por similitud
      con el criterio de EPIC-10.

### Proceso y accesibilidad
- [x] Miranda sigue la disciplina de revisión crítica de la skill
      `frontend-design` antes de codificar (aunque la dirección ya viene
      decidida por el usuario, no se salta la revisión de cómo se traduce
      a componentes reales), y toma capturas de autocrítica si su entorno
      lo permite.
- [x] Sin regresiones funcionales.
- [x] WCAG 2.1 AA mantenido: contraste de texto/UI verificado sobre los
      hexes nuevos (en particular `textSecondary` `#8fb8ae` sobre
      `bgVoid`/`surface`, y el acento `#34f5c1` como color de foco/estado
      sobre fondos oscuros), foco de teclado (`*:focus-visible`) visible
      con el nuevo acento.

## Alcance
Frontend (Miranda): `frontend/src/theme.ts`, `SiteHeader.tsx`,
`DashboardPage.tsx`, `ImagingViewerPage.tsx`, `ModelTrainingPage.tsx` y sus
tabs, `LoginCard.tsx`, `ResearchDisclaimerBanner.tsx`, `NiftiViewer.tsx`
(revisión visual, no cambio funcional). Uso de la skill `frontend-design`
como proceso de trabajo.

## Fuera de alcance
- Cualquier cambio de arquitectura de datos o backend.
- Cualquier Epic del roadmap de MLOps.
- Añadir páginas, pantallas o funcionalidad nueva que no exista ya hoy en
  el frontend.
- Volver a explorar direcciones de arte alternativas: la dirección
  "Bioluminescent Dark" ya fue elegida explícitamente por el usuario sobre
  un mood board de 3 opciones: esta Epic la construye tal cual la
  especificación, no la reinterpreta.

## Verificación
- `npm run lint`, `npm run build`, `npx vitest run` (28/28): todos re-ejecutados de forma
  independiente por el orquestador, en verde.
- Lectura directa de `theme.ts`: migración limpia, `quietSurface()`/`heroSurface(accent)`
  conservan firma exacta, tonos derivados recalculados formulaicamente (no a ojo),
  `chartColors.success` renombrado a `quaternary` para evitar colisión visual entre el verde
  de éxito antiguo y el nuevo verde bioluminiscente primario — confirmado sin referencias
  rotas al nombre anterior (`grep` en todo `frontend/src`).
- `NiftiViewer.tsx`: revisado con un arnés de contraste real (Playwright, capturas
  comparativas default vs. mutado) — el único punto de contacto real entre el acento verde y
  la imagen médica es el glow del `heroSurface` que lo envuelve; atenuado en
  `ImagingViewerPage.tsx` para no competir visualmente con la imagen ni con overlays rojos de
  hallazgos clínicos.
- Verificación visual real con capturas de Playwright (dashboard, login de viewer, login de
  training): paleta y tipografía coherentes. No se pudo capturar el visor con datos reales
  cargados (requiere backend + estudio real) — Miranda lo dejó explícito en vez de asumir.

### Ajuste post-cierre (fidelidad al mood board aprobado)
El usuario señaló, viendo capturas reales, que las tarjetas hero se veían con color plano y sin
sombra, mientras que la opción "Bioluminescent Dark" del mood board de 3 opciones
(`project/B-Bioluminescent.dc.html`) mostraba un glow radial anclado en la esquina superior
derecha (`radial-gradient(circle at 80% 0%, ...)` sobre el fondo oscuro) que se lee como un
degradado diagonal de abajo-izquierda a arriba-derecha. La implementación real de
`heroSurface()` en `theme.ts` nunca incorporó ese `backgroundImage` — se quedó solo con
`backgroundColor` plano + `box-shadow` — una desviación real frente a lo aprobado, no una
reinterpretación deliberada (la Epic no reabre la elección de dirección de arte, ver "Fuera de
alcance"; corrige la fidelidad de implementación a lo ya elegido). Corregido añadiendo el mismo
`radial-gradient` a `heroSurface(accent)` (reescalado a la opacidad del acento del tier hero) y
reforzando el `box-shadow` con una sombra de caída real además del glow direccional existente,
para que la tarjeta se despegue visualmente de la página. Las tarjetas `quietSurface()` (p. ej.
el dashboard) no cambian — el gradiente es exclusivo del tier hero, consistente con "un único
hero por pantalla". Verificado: `npm run lint`/`build`/`vitest run` (40/40) en verde, capturas
reales de `/admin/training` (hero) y `/` (dashboard, quiet, sin cambios) comparadas.

## Estado
Completada
