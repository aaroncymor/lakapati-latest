from django import forms

from .models import WaterConsumptionRecord


class WaterConsumptionRecordForm(forms.ModelForm):
    """
    Validates and coerces the client-submitted water billing fields.

    The config-derived snapshot fields (stored_fix_rate,
    stored_h2o_usage_cost_threshold) and stored_final_bill are intentionally
    excluded: they are computed on the server and must never be trusted from
    the client.
    """

    class Meta:
        model = WaterConsumptionRecord
        fields = [
            "start_date",
            "end_date",
            "previous_total",
            "current_total",
            "previous_usage",
            "current_usage",
            "apply_fix_rate",
            "stored_fix_rate",
            "stored_h2o_usage_cost_threshold",
            "stored_maintenance_fee",
            "stored_cost_per_h2o_usage",
            "maintenance_fee_note",
        ]
