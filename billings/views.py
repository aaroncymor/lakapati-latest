from dateutil.relativedelta import relativedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.core.paginator import Paginator

from properties.models import TenantGroup

from .forms import WaterConsumptionRecordForm
from .models import WaterConsumptionRecord


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _water_billing_modal_context(data, form=None):
    """
    Builds the water billing modal context from a submitted data mapping,
    coercing values to the types the Alpine x-data expects (ints / bool /
    strings). Used to re-render the modal after a validation failure.
    """
    return {
        "cycle_start_date": data.get("start_date", ""),
        "cycle_end_date": data.get("end_date", ""),
        "previous_total": _safe_int(data.get("previous_total")),
        "current_total": _safe_int(data.get("current_total")),
        "previous_usage": _safe_int(data.get("previous_usage")),
        "current_usage": _safe_int(data.get("current_usage")),
        "cost_per_h2o_usage": _safe_int(data.get("stored_cost_per_h2o_usage")),
        "maintenance_fee": _safe_int(data.get("stored_maintenance_fee")),
        "maintenance_fee_note": data.get("maintenance_fee_note", ""),
        "apply_fix_rate": data.get("apply_fix_rate") == "on",
        "stored_fix_rate": _safe_int(data.get("stored_fix_rate")),
        "open_modal": True,
        "form": form,
    }


# Create your views here.
def get_group_latest_waterbilling(
    request, tenant_group_id, *args, **kwargs
):
    """
    Gets latest recorded water consumption record for reference to
    next billing.
    """
    try:
        tenant_group = TenantGroup.objects.get(id=tenant_group_id)
        config = tenant_group.space.property.configuration
        fix_rate = config.water_billing_fix_rate
        threshold = config.h2o_usage_cost_threshold
        maintenance_fee = config.maintenance_fee
        cost_per_h2o_usage = config.cost_per_h2o_usage
    except TenantGroup.DoesNotExist:
        return HttpResponse(status=404)
    
    water_consumptions = WaterConsumptionRecord.objects.filter(
        tenant_group__id=tenant_group_id
    ).order_by("-created_at")[:1]

    
    water_consumption = None if not water_consumptions.count() else water_consumptions[0]

    context = {
        "previous_total": 0,
        "previous_usage": 0,
        "current_total": 0,
        "current_usage": 0,
        "apply_fix_rate": True,
        "fix_rate": fix_rate,
        "h2o_usage_cost_threshold": threshold,
        "stored_fix_rate": 0,
        "stored_maintenance_fee": 0,
        "stored_cost_per_h2o_usage": 0,
        "maintenance_fee": maintenance_fee,
        "cost_per_h2o_usage": cost_per_h2o_usage,
        "maintenance_fee_note": "",
        "open_modal": True
    }

    # determine cycle start and end dates
    cycle_start_date = None
    cycle_end_date = None
    if water_consumption:
        cycle_start_date = water_consumption.end_date
        
        # add one month to end date (make sure accurate number of days)
        cycle_end_date = water_consumption.end_date + relativedelta(months=1)

        # set context values
        context["cycle_start_date"] = cycle_start_date.strftime("%Y-%m-%d")
        context["cycle_end_date"] = cycle_end_date.strftime("%Y-%m-%d")
        context["previous_total"] = water_consumption.previous_total
        context["previous_usage"] = water_consumption.previous_usage
        context["current_total"] = water_consumption.current_total
        context["current_usage"] = water_consumption.current_usage
        context["apply_fix_rate"] = water_consumption.apply_fix_rate
        context["fix_rate"] = fix_rate
        context["h2o_usage_cost_threshold"] = threshold
        context["stored_fix_rate"] = water_consumption.stored_fix_rate
        context["stored_maintenance_fee"] = water_consumption.stored_maintenance_fee
        context["stored_cost_per_h2o_usage"] = water_consumption.stored_cost_per_h2o_usage
        context["maintenance_fee"] = water_consumption.maintenance_fee
        context["cost_per_h2o_usage"] = water_consumption.cost_per_h2o_usage
        context["maintenance_fee_note"] = water_consumption.maintenance_fee_note

    if request.htmx:
        return render(
            request, "properties/partials/water_billing_modal.html",
            context
        )

    return HttpResponse(status=400)


def detail_water_billing(request, pk, *args, **kwargs):
    if request.method == "GET":
        # Handle GET request
        water_consumption = WaterConsumptionRecord.objects.get(pk=pk)
        context = {
            "water_consumption": water_consumption
        }
        return render(
            request, "billings/water_billing_detail.html",
            context
        )
    return HttpResponse(status=400)


def create_water_billing(request, *args, **kwargs):
    if request.method != "POST":
        return HttpResponse(status=405)

    tenant_group = TenantGroup.objects.filter(
        pk=request.POST.get("tenant_group_id")
    ).first()
    if tenant_group is None:
        return HttpResponse(status=400)

    config = tenant_group.space.property.configuration

    form = WaterConsumptionRecordForm(request.POST)
    if not form.is_valid():
        # Re-render the modal (non-204) so htmx swaps it back in and it
        # stays open, repopulated with the submitted values and errors.
        context = _water_billing_modal_context(request.POST, form=form)
        return render(
            request, "properties/partials/water_billing_modal.html",
            context, status=400
        )

    record = form.save(commit=False)
    record.tenant_group = tenant_group

    # We allow the client to override these values via the form, but we also
    # snapshot them here to ensure they are consistent with the configuration.
    fix_rate = record.stored_fix_rate
    h2o_usage_cost_threshold = record.stored_h2o_usage_cost_threshold

    # Recompute the final bill server-side (mirrors the final_bill logic),
    # using the submitted/snapshotted values rather than a client-sent total.
    water_usage_diff = record.current_usage - record.previous_usage
    maintenance_fee = record.stored_maintenance_fee or 0
    cost_per_h2o_usage = record.stored_cost_per_h2o_usage or 0
    if (record.apply_fix_rate
            and water_usage_diff <= h2o_usage_cost_threshold):
        record.stored_final_bill = fix_rate + maintenance_fee
    else:
        record.stored_final_bill = (
            water_usage_diff * cost_per_h2o_usage
        ) + maintenance_fee

    record.save()

    # 204 No Content: htmx performs no swap; the modal closes
    # itself via hx-on::after-request on the form.
    return HttpResponse(status=204)


def get_billing_history(request, tenant_group_id, *args, **kwargs):
    if request.method != "GET":
        return HttpResponse(status=400)

    try:
        page_number = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page_number = 1

    water_billings = WaterConsumptionRecord.objects.filter(
        tenant_group_id=tenant_group_id
    ).order_by("-created_at")

    paginator = Paginator(water_billings, 25)
    page_obj = paginator.get_page(page_number)
    context = {
        "water_billings": page_obj,
        "page_obj": page_obj,
        "tenant_group_id": tenant_group_id,
        "open_modal": True
    }
    template = (
        "properties/partials/billing_history_modal.html"
        if page_number == 1
        else "properties/partials/billing_history_rows.html"
    )
    return render(request, template, context)