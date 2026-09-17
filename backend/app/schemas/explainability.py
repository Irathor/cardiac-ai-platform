from pydantic import BaseModel


class ExplainabilityShowcaseOut(BaseModel):
    """Passthrough of explainability_showcase.json (EPIC-1 offline script).

    Typed laxly on purpose — see EPIC-15 "Contrato técnico" point 3: the
    exact shape of the JSON is owned by
    ml/scripts/run_explainability_showcase.py, out of this Epic's scope to
    retype field by field (same rationale already used for
    ModelEvaluationOut.metrics)."""

    unet_seg_grad_cam: dict[str, object]
    cnn3d_grad_cam: dict[str, object]
    lime_shapley_panel: dict[str, object]
