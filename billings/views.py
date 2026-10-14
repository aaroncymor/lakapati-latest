from django.http import HttpResponse
from django.shortcuts import render
from properties.models import TenantGroup
from .models import WaterConsumptionRecord


# Create your views here.
def get_group_latest_waterbilling(
    request, tenant_group_id, *args, **kwargs
):
    water_consumptions = WaterConsumptionRecord.objects.filter(
        tenant_group__id=tenant_group_id
    ).order_by("-created_at")[:1]

    if request.htmx:
        water_consumption = None
        if water_consumptions.count() > 0:
            water_consumption = water_consumptions[0]
        return render(
            request, "properties/partials/water_billing_modal.html",
            {"water_consumption": water_consumption, "open_modal": True}
        )

    return HttpResponse(status=400)
