"""Stable field names for storage/API integration."""
DGE_INPUT_FIELDS = (
    "symbol","as_of","R","L","F","C","P","V","D","E","T",
    "spot_cvd","reclaim","oi_flush","supply_pressure","capital_efficiency","shock",
)
DGE_OUTPUT_FIELDS = (
    "schema_version","symbol","as_of","dominant_state","confidence",
    "p_accumulation","p_test","p_shakeout","p_markup","p_distribution","p_neutral",
)
