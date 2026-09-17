# EPIC-15: Showcase pedagógico LIME vs. Shapley en la web

## Historia de usuario
Como ingeniero de ML que presenta este proyecto como portfolio, quiero que el panel
comparativo LIME vs. Shapley que ya genera `ml/scripts/run_explainability_showcase.py` sea
visible en la web (no solo en un JSON/PNG local), para poder mostrarlo como parte del
recorrido del proyecto sin tener que ejecutar el script y enseñar archivos sueltos.

## Tipo
Normal. **No es una Epic "con IA"**: no se recalcula LIME ni Shapley en el request — se
sirven, de solo lectura, los artefactos ya generados offline por el script (que sí es donde
vive el cálculo real de IA, ya cubierto por EPIC-1). Exponer un archivo ya calculado por HTTP
es lógica de negocio determinista (leer, validar, servir), no una capacidad de IA nueva.

## Bloqueada por
EPIC-1 (Explicabilidad real — Grad-CAM + panel comparativo LIME vs. Shapley) — esta Epic
necesita que `data/models/explainability/explainability_showcase.json` y sus PNGs ya existan
en disco, generados por el script offline de EPIC-1.

## Criterios de aceptación
- [x] Nuevo endpoint de solo lectura `GET /api/v1/explainability/showcase` devuelve el
      contenido de `explainability_showcase.json` tal cual lo dejó el script (sin
      recalcular nada), incluyendo la sección `lime_shapley_panel` con las etiquetas
      `"LIME (aproximado)"`/`"Shapley (exacto)"` ya fijadas en EPIC-1/ADR-3.
- [x] Nuevo endpoint `GET /api/v1/explainability/showcase/images/{filename}` sirve cada PNG
      referenciado en ese JSON (`unet_gradcam_*`, `cnn3d_gradcam_*`), únicamente los
      archivos cuyo nombre aparece en el JSON ya cargado (sin aceptar una ruta arbitraria del
      cliente).
- [x] Si el archivo `explainability_showcase.json` no existe en este entorno (el script
      offline nunca se ejecutó — p. ej. un entorno de CI/desarrollo sin GPU ni checkpoints),
      el endpoint responde 404 con un mensaje honesto indicando cómo generarlo, en vez de
      fabricar o simular un resultado.
- [x] Nueva página `/explainability-showcase`, separada de los flujos clínicos reales
      (`/viewer`) y del área de administración de modelos (`/admin/training`), que muestra el
      panel LIME vs. Shapley (lado a lado, con las etiquetas de aproximado/exacto) y los
      mapas Grad-CAM de U-Net/CNN3D del showcase, con un aviso visual **inequívoco y
      permanente en la parte superior de la página** (no un tooltip ni una nota al pie): "Esta
      página es una comparación pedagógica offline, no una explicación de producción — ver
      ADR-3". Nunca se referencia desde `/viewer` ni desde el informe de un `AIAnalysis` real.
- [x] Enlace a esta página únicamente desde una zona no clínica de la navegación (p. ej. el
      área de administración/engineering), nunca desde el flujo del médico.
- [x] Antes de marcar esta Epic como Completada, el orquestador ejecuta el skill
      `security-review` sobre el diff completo (endpoint nuevo de lectura de ficheros con
      validación de path traversal en `/images/{filename}`, ver "Contrato técnico" punto 4) —
      no se cierra sin ese resultado, aunque los tests de Tali/Mordin ya pasen.

## Alcance
Backend (`backend/app/api/v1/explainability.py` nuevo, `backend/app/schemas/explainability.py`
nuevo) y frontend (`frontend/src/pages/ExplainabilityShowcasePage.tsx` nuevo,
`frontend/src/api/explainability.ts` nuevo, entrada de navegación nueva en `SiteHeader`).

## Fuera de alcance
- Recalcular LIME/Shapley bajo demanda o en tiempo real — sigue siendo estrictamente offline
  (ver ADR-3 y EPIC-1); esta Epic solo sirve lo ya generado.
- LIME sobre imágenes — descartado en ADR-3, registrado en `docs/BACKLOG.md`.
- Cambiar `ml/scripts/run_explainability_showcase.py` o el formato que produce — se consume
  tal cual.
- Overlay de Grad-CAM en el visor real — eso es EPIC-14 (dato real servido, no el showcase).

## Verificación
- `backend`: 148/148 tests en verde, `ruff check` limpio.
- `security-review` (skill del orquestador): revisó las tres capas de defensa contra path
  traversal en `load_showcase_image_bytes` (rechazo de `/`/`\`/`..`, allowlist exacta contra
  basenames del JSON, comprobación final de `resolve()`), probó mentalmente filename vacío,
  secuencias Unicode, null bytes y nombres largos — sin bypass encontrado. RBAC confirmado
  (`ML_ENGINEER`/`MODEL_APPROVER`/`ADMIN`, `DOCTOR` excluido a propósito).
- **Bug real encontrado y arreglado en este checkpoint, fuera de lo que cubrió
  `security-review`** (no es un hallazgo de seguridad, es de correctitud cross-plataforma):
  `explainability_showcase.json` se generó en este host Windows con `png_path` usando `\`
  como separador; el backend corre en Linux dentro del contenedor, donde `pathlib.Path` no
  trata `\` como separador, así que `_allowed_image_basenames` extraía la ruta completa en
  vez del nombre de archivo, y el endpoint de imágenes devolvía 404 siempre. Detectado
  verificando la página real end-to-end (no solo tests unitarios con fixtures ya
  normalizados) tras una observación directa del usuario ("no se ven imágenes"). Arreglado
  con un split explícito sobre ambos separadores (`_basename()`), sin debilitar ninguna de
  las tres capas de seguridad ya revisadas — verificado con la imagen real sirviéndose
  correctamente (200, 290KB) y con las 4 imágenes reales cargando sin errores de consola en
  la página `/explainability-showcase` real (Playwright, captura revisada).
- Tests re-ejecutados tras el fix: 10/10 en `test_explainability_api.py`, `ruff` limpio.

## Estado
Completada

## Contrato técnico (Shepard)

### 1. Por qué un endpoint de solo lectura y no archivos estáticos servidos directamente
El contenedor `backend` ya monta `./data:/data` (ver `docker-compose.yml`, mismo mount que
usa `dl_inference_client.py` vía `settings.data_root`), así que
`data/models/explainability/` ya es alcanzable desde el proceso backend sin tocar
`docker-compose.yml` ni pedir nada a Garrus. Se pasa por un endpoint de la API (en vez de,
p. ej., que el frontend pida el archivo a un servidor estático nuevo) para reutilizar el
mismo mecanismo de auth/RBAC que el resto de la plataforma y no abrir una ruta de archivos
sin autenticar.

### 2. Endpoints — RBAC y forma exacta

`backend/app/api/v1/explainability.py`, RBAC: reutiliza exactamente `_VIEW_ROLES =
(ML_ENGINEER, MODEL_APPROVER, ADMIN)` de `app/api/v1/models.py` — este showcase es un
artefacto de ingeniería/gobernanza de modelos, no una herramienta clínica, así que no se le
da acceso a `DOCTOR`.

```
GET /api/v1/explainability/showcase
  -> 200 ExplainabilityShowcaseOut (passthrough del JSON, ver punto 3)
  -> 404 si el archivo no existe: detail="Explainability showcase not generated in this
     environment. Run ml/scripts/run_explainability_showcase.py first."

GET /api/v1/explainability/showcase/images/{filename}
  -> 200 Response(content=<bytes PNG>, media_type="image/png")
  -> 404 si `filename` no es exactamente uno de los basenames de `png_path` ya presentes en
     el JSON cargado (ver punto 4, protección contra path traversal)
```

Declarados en un router nuevo montado en `app/api/v1/__init__.py` junto al resto (mismo
patrón que `models.py`/`analysis.py`).

### 3. Schema — passthrough tipado laxo, no replicar cada campo del script

`ExplainabilityShowcaseOut` en `app/schemas/explainability.py`: dado que la forma exacta del
JSON la define `ml/scripts/run_explainability_showcase.py` (EPIC-1, ya cerrada y fuera del
alcance de esta Epic tocarla), no tiene sentido que Tali retipe cada campo a mano y quede
acoplada a cambios futuros del script — mismo criterio ya usado para `ModelEvaluationOut.
metrics` (JSON columna, tipado laxo). Firma:
```python
class ExplainabilityShowcaseOut(BaseModel):
    unet_seg_grad_cam: dict[str, object]
    cnn3d_grad_cam: dict[str, object]
    lime_shapley_panel: dict[str, object]
```
Basta con que las tres claves de primer nivel existan (son las que ya escribe `main()` del
script) — el frontend accede a los campos internos (`patient_id`, `method_attributions`,
etc.) con el tipo específico que Miranda defina en el cliente TS, sabiendo que viene de un
artefacto offline versionado por EPIC-1, no de un contrato API estricto.

### 4. Protección contra path traversal en `/images/{filename}`

El endpoint de imagen **nunca** concatena `filename` directo a una ruta de disco sin
validar. Al servir, primero se carga `explainability_showcase.json` (si no existe, 404 igual
que el endpoint de arriba), se recolectan los basenames de todos los `png_path` presentes
(`Path(v["png_path"]).name` para cada estructura de `unet_seg_grad_cam.structures` y para
`cnn3d_grad_cam.png_path`), y solo si `filename` coincide **exactamente** con uno de esos
basenames se lee `Path(settings.data_root) / "models" / "explainability" / filename` — nunca
se acepta `filename` con `/`, `..` o cualquier separador (rechazado aunque coincidiera por
casualidad, como guardarraíl explícito además del allowlist). Esto es exactamente el tipo de
endpoint nuevo con acceso a datos en disco que activa la regla de "antes de cerrar cualquier
Epic que toque... endpoints expuestos públicamente" — **Tali debe señalarlo a Shepard y el
orquestador ejecuta el skill `security-review`** antes de dar esta Epic por Completada.

### 5. Frontend — página separada, nunca dentro de un flujo clínico

`frontend/src/pages/ExplainabilityShowcasePage.tsx`, ruta nueva `/explainability-showcase` en
`frontend/src/app/App.tsx`. Estructura: un `Alert severity="warning"` fijo en la parte
superior (no descartable, siempre visible mientras la página está montada) con el texto de
ADR-3; debajo, dos secciones `quietSurface()` — una con los Grad-CAM de U-Net/CNN3D (imagen
servida desde `/showcase/images/{filename}`), otra con el panel LIME vs. Shapley (tabla o
chips lado a lado por método, con las etiquetas `"LIME (aproximado)"`/`"Shapley (exacto)"`
tal cual las devuelve el JSON — nunca renombradas a algo que suene a producción). Accento
`violet` (dominio "mirando al modelo", igual que `ModelTrainingPage`), consistente con que
esto es un artefacto de ingeniería de modelos, no clínico. Enlace nuevo en `SiteHeader.tsx`
únicamente en la zona de navegación de administración/engineering (junto al enlace a
`/admin/training`), nunca junto al enlace a `/viewer`.

### 6. División de trabajo
- **Tali** (`backend/`): los dos endpoints, el schema, el allowlist de path traversal, tests
  (incluye el 404 honesto sin el archivo, el 404 de `filename` no permitido, RBAC).
- **Miranda** (`frontend/`): la página nueva, el cliente API, el enlace de navegación.
- No hace falta EDI (no se toca `ml/`) ni Garrus (sin cambios de infraestructura).
- Paralelizable: Miranda puede avanzar contra el contrato de arriba con un JSON de fixture
  mientras Tali implementa el endpoint real.

### 7. Verificación
Al cierre: `security-review` obligatorio (ver punto 4) sobre el diff completo antes de marcar
Completada, además de los tests normales de Tali/Mordin.
