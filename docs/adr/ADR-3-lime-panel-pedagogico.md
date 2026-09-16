# ADR-3: LIME solo como panel pedagógico comparativo, no en producción

## Estado
Aceptada

## Contexto
El clasificador de biomarcadores (nearest-centroid, `ml/cardiac_ai_ml/classification.py:120-159`)
ya cuenta con explicabilidad mediante **Shapley values exactos** — no aproximados, porque el
espacio de 4 features (fracción de eyección, volumen telediastólico de VI/VD, masa
miocárdica) es tratable por fuerza bruta (16 coaliciones posibles).

LIME es un método de aproximación local mediante muestreo y un modelo sustituto lineal.
Aplicado sobre este mismo clasificador, sería estrictamente peor que la explicación exacta
ya existente: introduciría varianza y aproximación donde ya hay un resultado exacto.

Se valoraron tres opciones:
1. No implementar LIME en absoluto.
2. Implementar LIME únicamente como panel comparativo pedagógico ("aproximado (LIME) vs.
   exacto (Shapley)") sobre el clasificador de biomarcadores, con fines demostrativos del
   showcase.
3. Aplicar LIME sobre las imágenes (CNN3D/U-Net) como complemento de Grad-CAM.

## Decisión
El usuario elige la opción 2: se implementa LIME **únicamente como panel comparativo
pedagógico** sobre el clasificador de biomarcadores, mostrando lado a lado el resultado
aproximado (LIME) y el resultado exacto (Shapley), con el objetivo de demostrar que el
equipo entiende la diferencia entre explicabilidad exacta y aproximada. Este panel **nunca**
se usa como la explicación real servida al usuario final ni sustituye a Shapley en ningún
flujo de producción — Shapley sigue siendo la única explicación de producción para este
clasificador.

Se descartan las opciones 1 y 3: la opción 1 renuncia a una pieza de showcase de bajo coste
y con valor pedagógico claro; la opción 3 (LIME sobre imágenes, como complemento de
Grad-CAM) queda fuera de alcance por ahora — puede volver a proponerse más adelante si se
identifica algo concreto que aporte sobre lo que ya cubre Grad-CAM, pero no se implementa en
esta fase del roadmap.

## Consecuencias
- Alcance deliberadamente acotado: LIME no se aplica a los modelos de imagen (CNN3D/U-Net)
  en esta fase del roadmap — esa dirección queda registrada en `docs/BACKLOG.md` como
  "Fuera de alcance", con este ADR como motivo, para no perderla ni re-litigarla sin
  contexto nuevo.
- El panel LIME vs. Shapley debe quedar etiquetado de forma inequívoca en la UI/salida como
  comparación pedagógica, para que no se confunda con una explicación de producción.
- No hay impacto en el flujo de inferencia servido: Shapley sigue siendo el único mecanismo
  de explicabilidad que llega al informe clínico/showcase real.
