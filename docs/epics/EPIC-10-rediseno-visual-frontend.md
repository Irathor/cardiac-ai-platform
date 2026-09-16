# EPIC-10: Rediseño visual del frontend hacia un tema oscuro "AI-Ops" moderno y cercano

## Historia de usuario
Como usuario que va a mostrar esta plataforma como pieza insignia de su
portfolio de AI/ML Engineering, quiero que el frontend mantenga su
identidad oscura "AI-Ops" futurista-médica pero con un acabado más
cercano, atractivo y moderno (en la línea de los dashboards de referencia
Neurix y NexaCore), para que la primera impresión visual esté a la altura
del trabajo técnico real que hay detrás (MRI → preprocessing →
segmentación → biomarcadores → modelo → predicción → explicabilidad →
informe, con MLOps real).

## Tipo
Normal

## Bloqueada por
Ninguna

## Criterios de aceptación
- [x] Existe un documento de dirección de diseño (token system: paleta de
      color con roles claros — fondo, superficie, acento primario/
      secundario, estados—, escala tipográfica, escala de espaciado/
      layout, y principios de jerarquía visual) producido siguiendo el
      proceso de dos pasadas de la skill `frontend-design` (primera
      pasada amplia con varias direcciones, segunda pasada refinando la
      dirección elegida), con revisión crítica explícita antes de
      codificar. Documentado como comentario de cabecera en
      `frontend/src/theme.ts` y en el resumen de cierre de Miranda: dos
      ideas estructurales — acento por dominio (cian = clínico/paciente,
      violeta = MLOps/modelo) y dos niveles de elevación deliberados
      (`quietSurface()`/`heroSurface()`, un único hero por pantalla).
- [x] El nuevo token system queda aplicado en `frontend/src/theme.ts` —
      exporta `tokens`, `quietSurface()`, `heroSurface(accent)` y
      sustituye la paleta/tipografía anterior por completo, no convive
      como alternativa sin usar.
- [x] Se rompe explícitamente el patrón "SaaS-card kit genérico": `MuiCard`
      usa `quietSurface()` por defecto (plano, borde fino, sin sombra) y
      `heroSurface()` se reserva explícitamente al elemento focal de cada
      pantalla (visor NIfTI, card de retrain, login, métrica líder de
      `SummaryTab`) — dos niveles de énfasis reales, documentados en el
      propio `theme.ts`.
- [x] El rediseño se aplica de verdad a: tema global, `SiteHeader.tsx`,
      `DashboardPage.tsx`, `ImagingViewerPage.tsx`, `ModelTrainingPage.tsx`
      y sus tabs — `ClassificationTab`/`CalibrationTab`/`ValidationTab` no
      necesitaron cambios propios porque ya heredan el tema vía
      componentes MUI/tokens compartidos (`chartColors`/`heatCellColor`)
      sin color hardcodeado, verificado por inspección directa.
- [x] `LoginCard.tsx` y `ResearchDisclaimerBanner.tsx` quedan coherentes
      con el nuevo tema (`ResearchDisclaimerBanner` ya heredaba de MUI/
      tokens compartidos, sin cambios propios necesarios).
- [x] Tells genéricos evitados: cabeceras de tabla en sentence case (ya
      no mayúsculas trackeadas), sin em-dash genérico en subtítulos de
      estado (chip propio en vez de "AI analysis — {status}"), sin
      blur/glow repetido sin criterio (glow reservado a `heroSurface`).
- [x] Sin regresiones funcionales — ver verificación abajo.
- [x] `NiftiViewer.tsx` sigue legible tras el rediseño (no tocado
      directamente; contraste del visor clínico verificado visualmente
      por Miranda y de forma independiente por el orquestador vía
      capturas).
- [x] Resumen de cierre documenta el proceso `frontend-design`: paleta
      con roles, jerarquía quiet/hero, tells evitados y por qué, capturas
      reales tomadas con Playwright (Dashboard escritorio/móvil, Viewer,
      Training) — ver mensaje de cierre de Miranda.
- [x] Accesibilidad: `*:focus-visible` con outline cian explícito añadido
      globalmente en `theme.ts`; contraste revisado visualmente; sin
      motion nueva que requiera `prefers-reduced-motion` (el único cambio
      de motion es el pulso de estado en vivo, ya respetuoso).

## Alcance
Frontend (Miranda): `frontend/src/theme.ts`, `SiteHeader.tsx`,
`DashboardPage.tsx`, `ImagingViewerPage.tsx`, `ModelTrainingPage.tsx` y
sus tabs, `LoginCard.tsx`, `ResearchDisclaimerBanner.tsx`,
`NiftiViewer.tsx` (ajuste visual, no funcional). Uso de la skill
`frontend-design` como proceso de trabajo para esta Epic.

## Fuera de alcance
- Cualquier cambio de arquitectura de datos o backend.
- Cualquier Epic del roadmap de MLOps (EPIC-3 a EPIC-9): esta Epic no
  adelanta ni sustituye ninguna de ellas.
- Añadir páginas, pantallas o funcionalidad nueva que no exista ya hoy en
  el frontend: esto es un rediseño visual sobre lo existente, no una
  feature nueva.
- Cambiar a un tema claro (tipo "Medico"): descartado explícitamente por
  el usuario en la conversación previa a esta Epic — se mantiene el tema
  oscuro.

## Verificación
- `npm run lint`: limpio (re-ejecutado de forma independiente por el
  orquestador, no solo aceptado del informe de Miranda).
- `npm run build` (`tsc -b && vite build`): build correcto; único warning
  es tamaño de chunk >500kB, preexistente y no relacionado con esta Epic.
- `npx vitest run`: 28/28 tests en verde en 10 archivos (re-ejecutado de
  forma independiente), incluido el fix del test de `ImagingViewerPage`
  (aserción ambigua `getByText(/AI analysis/)` → `getByRole("heading", ...)`
  tras el cambio de wording del subtítulo de estado).
- Verificación visual real por Miranda con `npm run dev` +
  `npx playwright screenshot` (Dashboard escritorio y móvil 390px, Viewer
  con login, Training con login): tema oscuro coherente, jerarquía hero/
  quiet visible, sin overflow horizontal en móvil, foco/contraste legibles.
- Revisión directa de `theme.ts` por el orquestador: sistema de tokens
  coherente, jerarquía quiet/hero real y no cosmética, foco de teclado
  explícito, tells genéricos evitados de verdad.

## Estado
Completada
