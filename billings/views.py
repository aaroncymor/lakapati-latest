from dateutil.relativedelta import relativedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.core.paginator import Paginator

from .models import WaterConsumptionRecord


# Create your views here.
def get_group_latest_waterbilling(
    request, tenant_group_id, *args, **kwargs
):
    """
    Gets latest recorded water consumption record for reference to
    next billing.
    """
    water_consumptions = WaterConsumptionRecord.objects.filter(
        tenant_group__id=tenant_group_id
    ).order_by("-created_at")[:1]


    water_consumption = None if not water_consumptions.count() else water_consumptions[0]

    context = {
        "previous_total": 0,
        "previous_usage": 0,
        "current_total": 0,
        "current_usage": 0,
        "stored_maintenance_fee": 0,
        "stored_cost_per_h2o_usage": 0,
        "maintenance_fee": 0,
        "cost_per_h2o_usage": 0,
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
        context["stored_maintenance_fee"] = water_consumption.stored_maintenance_fee
        context["stored_cost_per_h2o_usage"] = water_consumption.stored_cost_per_h2o_usage
        context["maintenance_fee"] = water_consumption.maintenance_fee
        context["cost_per_h2o_usage"] = water_consumption.cost_per_h2o_usage

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
    if request.method == "POST":
        # Handle POST request
        tenant_group_id = request.POST.get("tenant_group_id")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        previous_total = request.POST.get("previous_total")
        current_total = request.POST.get("current_total")
        previous_usage = request.POST.get("previous_usage")
        current_usage = request.POST.get("current_usage")
        stored_maintenance_fee = request.POST.get("stored_maintenance_fee")
        stored_cost_per_h2o_usage = request.POST.get("stored_cost_per_h2o_usage")
        stored_final_amount = request.POST.get("stored_final_amount")

        try:
            WaterConsumptionRecord.objects.create(
                tenant_group_id=tenant_group_id,
                start_date=start_date,
                end_date=end_date,
                previous_total=previous_total,
                current_total=current_total,
                previous_usage=previous_usage,
                current_usage=current_usage,
                stored_maintenance_fee=stored_maintenance_fee,
                stored_cost_per_h2o_usage=stored_cost_per_h2o_usage,
                stored_final_bill=stored_final_amount
            )
        except Exception as e:
            print(e)
            return HttpResponse(status=500)

        # 204 No Content: htmx performs no swap; the modal closes
        # itself via hx-on::after-request on the form.
        return HttpResponse(status=204)

    return HttpResponse(status=405)


def get_billing_history(request, tenant_group_id, *args, **kwargs):
    if request.method == "GET":

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
            "open_modal": True
        }
        return render(
            request, "properties/partials/billing_history_modal.html",
            context
        )
    return HttpResponse(status=400)