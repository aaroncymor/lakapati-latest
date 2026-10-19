import json
import pandas as pd
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
        response = render(
            request, "properties/partials/water_billing_modal.html", context, 
            status=400
        )
        response["HX-Trigger"] = json.dumps({
            "toast": {"type": "error", "message": "Please correct the highlighted fields."}
        })
        return response

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
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"type": "success", "message": "Water billing saved successfully."}
    })
    return response


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


def download_water_billings_template(request, *args, **kwargs):
    if request.method != 'GET':
        return HttpResponse(status=400)
    
    tenant_groups = TenantGroup.objects.filter(is_active=True)
    
    # downloadable excel file with following rows:
    # tenant_group_id, tenant_group_name, property_and_space, 
    # start_date, end_date, previous_total, current_total, previous_usage, 
    # current_usage, apply_fix_rate, fix_rate, h2o_usage_cost_threshold, 
    # cost_per_h2o_usage, maintenance_fee, maintenance_fee_note
    columns = [
        'tenant_group_id', 'tenant_group_name', 'property_and_space',
        'start_date', 'end_date', 'previous_total', 'current_total',
        'previous_usage', 'current_usage', 'apply_fix_rate', 'fix_rate',
        'h2o_usage_cost_threshold', 'cost_per_h2o_usage', 'maintenance_fee',
        'maintenance_fee_note'
    ]
    
    # Placeholder row as guidance for user
    placeholder_row = {
        'tenant_group_id': '(Do not edit)',
        'tenant_group_name': '(Do not edit)',
        'property_and_space': '(Do not edit)',
        'start_date': 'YYYY-MM-DD (e.g. 2025-10-01)',
        'end_date': 'YYYY-MM-DD (e.g. 2025-10-31)',
        'previous_total': '100',
        'current_total': '110',
        'previous_usage': '50',
        'current_usage': '55',
        'apply_fix_rate': 'TRUE/FALSE',
        'fix_rate': '100',
        'h2o_usage_cost_threshold': '100',
        'cost_per_h2o_usage': '60',
        'maintenance_fee': '300',
        'maintenance_fee_note': 'Optional (e.g., 7 days)',
    }

    data = [placeholder_row]
    for tenant_group in tenant_groups:
        space = tenant_group.space
        property = space.property
        property_and_space = f"{property.name} - {space.name}"

        config = property.configuration
        config_maintenance_fee = config.maintenance_fee
        config_fix_rate = config.water_billing_fix_rate
        config_h2o_usage_cost_threshold = config.h2o_usage_cost_threshold
        config_cost_per_h2o_usage = config.cost_per_h2o_usage

        # get latest recorded water billing for this tenant group
        start_date = ""
        end_date = ""
        previous_total = 0
        current_total = 0
        previous_usage = 0
        current_usage = 0
        apply_fix_rate = True
        fix_rate = config_fix_rate
        h2o_usage_cost_threshold = config_h2o_usage_cost_threshold
        cost_per_h2o_usage = config_cost_per_h2o_usage
        maintenance_fee = config_maintenance_fee
        maintenance_fee_note = ""

        latest_water_billing = WaterConsumptionRecord.objects.filter(
            tenant_group=tenant_group
        ).order_by('-created_at').first()
        if latest_water_billing:
            start_date = latest_water_billing.end_date
            end_date = latest_water_billing.end_date + relativedelta(months=1)
            previous_total = latest_water_billing.previous_total
            current_total = latest_water_billing.current_total
            previous_usage = latest_water_billing.previous_usage
            current_usage = latest_water_billing.current_usage

        data.append({
            'tenant_group_id': str(tenant_group.id),
            'tenant_group_name': tenant_group.name,
            'property_and_space': property_and_space,
            'start_date': start_date.strftime('%Y-%m-%d') if start_date else "",
            'end_date': end_date.strftime('%Y-%m-%d') if end_date else "",
            'previous_total': previous_total,
            'current_total': current_total,
            'previous_usage': previous_usage,
            'current_usage': current_usage,
            'apply_fix_rate': apply_fix_rate,
            'fix_rate': fix_rate,
            'h2o_usage_cost_threshold': h2o_usage_cost_threshold,
            'cost_per_h2o_usage': cost_per_h2o_usage,
            'maintenance_fee': maintenance_fee,
            'maintenance_fee_note': maintenance_fee_note,
        })

    df = pd.DataFrame(data)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="water_billings_template.xlsx"'
    df.to_excel(response, index=False, engine='openpyxl')

    return response


def import_water_billings(request, *args, **kwargs):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']

        # Validate file type - only allow Excel files
        allowed_mimetypes = [
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.oasis.opendocument.spreadsheet',
        ]
        if uploaded_file.content_type not in allowed_mimetypes:
            response = HttpResponse(status=200)
            response["HX-Trigger"] = json.dumps({
                "toast": {"type": "error", "message": "Invalid file type. Please upload an Excel file."}
            })
            return response
        
        # read the file
        df = pd.read_excel(uploaded_file)
        
        # loop through the rows, skipping the header (index 0) which is the placeholder row
        for idx, row in df.iterrows():
            # Skip the first row (placeholder/guidance row from template)
            if idx == 0:
                continue
            
            # Skip rows where tenant_group_id contains placeholder text
            tenant_group_id = str(row['tenant_group_id']).strip()
            if tenant_group_id == '(Do not edit)' or not tenant_group_id:
                continue
                
            # The start_date and end_date must not be existing in the database
            if WaterConsumptionRecord.objects.filter(
                tenant_group_id=tenant_group_id,
                start_date=row['start_date'], 
                end_date=row['end_date']
            ).exists():
                continue
            
            try:
                # Compute stored_final_bill server-side
                water_usage_diff = int(row['current_usage']) - int(row['previous_usage'])
                maintenance_fee = int(row['maintenance_fee']) if pd.notna(row['maintenance_fee']) else 0
                cost_per_h2o_usage = int(row['cost_per_h2o_usage']) if pd.notna(row['cost_per_h2o_usage']) else 0
                fix_rate = int(row['fix_rate']) if pd.notna(row['fix_rate']) else 0
                h2o_usage_cost_threshold = int(row['h2o_usage_cost_threshold']) if pd.notna(row['h2o_usage_cost_threshold']) else 0
                apply_fix_rate = str(row['apply_fix_rate']).upper() in ('TRUE', '1', 'YES')
                
                if apply_fix_rate and water_usage_diff <= h2o_usage_cost_threshold:
                    stored_final_bill = fix_rate + maintenance_fee
                else:
                    stored_final_bill = (water_usage_diff * cost_per_h2o_usage) + maintenance_fee
                
                WaterConsumptionRecord.objects.create(
                    tenant_group_id=tenant_group_id,
                    start_date=row['start_date'],
                    end_date=row['end_date'],
                    previous_total=int(row['previous_total']),
                    current_total=int(row['current_total']),
                    previous_usage=int(row['previous_usage']),
                    current_usage=int(row['current_usage']),
                    apply_fix_rate=apply_fix_rate,
                    stored_fix_rate=fix_rate,
                    stored_h2o_usage_cost_threshold=h2o_usage_cost_threshold,
                    stored_cost_per_h2o_usage=cost_per_h2o_usage,
                    stored_maintenance_fee=maintenance_fee,
                    maintenance_fee_note=row['maintenance_fee_note'] if pd.notna(row['maintenance_fee_note']) else '',
                    stored_final_bill=stored_final_bill,
                )
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
        
        # Process the file here
        # For now, just return a success message
        response = HttpResponse(status=200)
        response["HX-Trigger"] = json.dumps({
            "toast": {"type": "success", "message": "Water billing imported successfully."}
        })
        return response
    
    response = HttpResponse(status=200)
    response["HX-Trigger"] = json.dumps({
        "toast": {"type": "error", "message": "No file uploaded."}
    })
    return response
