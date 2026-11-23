import json
import pandas as pd
from dateutil.relativedelta import relativedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.core.paginator import Paginator

from properties.models import TenantGroup

from .forms import WaterConsumptionRecordForm, ElectricityConsumptionRecordForm
from .models import WaterConsumptionRecord, ElectricityConsumptionRecord


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

class BillingImportError(Exception):
    pass

def _validate_file_type(uploaded_file):
    allowed_mimetypes = [
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.oasis.opendocument.spreadsheet',
    ]
    if uploaded_file.content_type not in allowed_mimetypes:
        raise BillingImportError("Invalid file type. Please upload an Excel file.")

def _validate_date_range(df):
    # imported file must have same start_date and end_date for all rows.
    # Skip the placeholder/guidance row (index 0) and any empty rows.
    data = df.iloc[1:][['start_date', 'end_date']].dropna()
    unique_date_ranges = data.drop_duplicates()
    if len(unique_date_ranges) > 1:
        raise BillingImportError("All rows must have the same start_date and end_date.")


def import_water_billings(uploaded_file):
    # Validate file type - only allow Excel files
    _validate_file_type(uploaded_file)

    # read the file
    df = pd.read_excel(uploaded_file)

    # Validate date range
    _validate_date_range(df)

    # get previous total and current total by sum of previous_usage and current_usage
    # must be same start_date and end_date for all rows
    # (cast to float: pandas .sum() returns a numpy scalar that Decimal() rejects)
    previous_total = float(df.iloc[1:]['previous_usage'].sum())
    current_total = float(df.iloc[1:]['current_usage'].sum())
    
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
            usage_diff = float(row['current_usage']) - float(row['previous_usage'])
            maintenance_fee = float(row['maintenance_fee']) if pd.notna(row['maintenance_fee']) else 0
            cost_per_h2o_usage = float(row['cost_per_h2o_usage']) if pd.notna(row['cost_per_h2o_usage']) else 0
            fix_rate = float(row['fix_rate']) if pd.notna(row['fix_rate']) else 0
            h2o_usage_cost_threshold = int(row['h2o_usage_cost_threshold']) if pd.notna(row['h2o_usage_cost_threshold']) else 0
            apply_fix_rate = str(row['apply_fix_rate']).upper() in ('TRUE', '1', 'YES')
            
            if apply_fix_rate and usage_diff <= h2o_usage_cost_threshold:
                stored_final_bill = fix_rate + maintenance_fee
            else:
                stored_final_bill = (usage_diff * cost_per_h2o_usage) + maintenance_fee
            
            WaterConsumptionRecord.objects.create(
                tenant_group_id=tenant_group_id,
                start_date=row['start_date'],
                end_date=row['end_date'],
                previous_total=previous_total,
                current_total=current_total,
                previous_usage=float(row['previous_usage']),
                current_usage=float(row['current_usage']),
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


def import_electricity_billings(uploaded_file):
    _validate_file_type(uploaded_file)

    # read the file
    df = pd.read_excel(uploaded_file)

    # Validate date range
    _validate_date_range(df)
    
    # get previous total and current total by sum of previous_usage and current_usage
    # must be same start_date and end_date for all rows
    previous_total = float(df.iloc[1:]['previous_usage'].sum())
    current_total = float(df.iloc[1:]['current_usage'].sum())
    
    # loop through the rows, skipping the header (index 0) which is the placeholder row
    for idx, row in df.iterrows():
        # Skip the first row (placeholder/guidance row from template)
        if idx == 0:
            continue

        tenant_group_id = row.get("tenant_group_id")
        if not tenant_group_id:
            continue

        # The start_date and end_date must not be existing in the database
        if ElectricityConsumptionRecord.objects.filter(
            tenant_group_id=tenant_group_id,
            start_date=row['start_date'], 
            end_date=row['end_date']
        ).exists():
            continue

        try:
            usage_diff = float(row['current_usage']) - float(row['previous_usage'])
            head_count = int(row['head_count']) if pd.notna(row['head_count']) else 0
            if not head_count:
                tenant_group = TenantGroup.objects.get(id=tenant_group_id)
                head_count = tenant_group.tenants.count()
            multiply_by_head_count = bool(row['multiply_by_head_count']) if pd.notna(row['multiply_by_head_count']) else True
            cost_per_electricity_usage = float(row['cost_per_electricity_usage']) if pd.notna(row['cost_per_electricity_usage']) else 0.0
            common_usage_per_head = float(row['common_usage_per_head']) if pd.notna(row['common_usage_per_head']) else 0.0
            fixed_water_fee = float(row['fixed_water_fee']) if pd.notna(row['fixed_water_fee']) else 0.0
            
            final_bill = (
                (usage_diff * cost_per_electricity_usage) 
                + (common_usage_per_head * head_count if multiply_by_head_count else common_usage_per_head)
                + (fixed_water_fee * head_count if multiply_by_head_count else fixed_water_fee)
            )
            
            # Create the record
            ElectricityConsumptionRecord.objects.create(
                tenant_group_id=tenant_group_id,
                start_date=row['start_date'],
                end_date=row['end_date'],
                previous_total=float(previous_total),
                current_total=float(current_total),
                previous_usage=float(row['previous_usage']),
                current_usage=float(row['current_usage']),
                stored_head_count=head_count,
                stored_multiply_by_head_count=multiply_by_head_count,
                stored_cost_per_electricity_usage=cost_per_electricity_usage,
                stored_common_usage_per_head=common_usage_per_head,
                stored_fixed_water_fee=fixed_water_fee,
                stored_final_bill=final_bill,
            )
        except (ValueError, TypeError) as e:
            print(f"Error processing row {idx}: {e}")


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

def _electricity_billing_modal_context(data, form=None):
    """
    Builds the electricity billing modal context from a submitted data mapping,
    coercing values to the types the Alpine x-data expects (ints / bool /
    strings). Used to re-render the modal after a validation failure.
    """
    return {
        "cycle_start_date": data.get("start_date", ""),
        "cycle_end_date": data.get("end_date", ""),
        "previous_total": _safe_float(data.get("previous_total")),
        "current_total": _safe_float(data.get("current_total")),
        "previous_usage": _safe_float(data.get("previous_usage")),
        "current_usage": _safe_float(data.get("current_usage")),
        "cost_per_electricity_usage": _safe_float(data.get("stored_cost_per_electricity_usage")),
        "maintenance_fee": _safe_float(data.get("stored_maintenance_fee")),
        "maintenance_fee_note": data.get("maintenance_fee_note", ""),
        "multiply_by_head_count": data.get("stored_multiply_by_head_count") == "on",
        "common_usage_per_head": _safe_float(data.get("stored_common_usage_per_head")),
        "fixed_water_fee": _safe_float(data.get("stored_fixed_water_fee")),
        "head_count": _safe_int(data.get("stored_head_count")),
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


    latest = None if not water_consumptions.count() else water_consumptions[0]

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
    if latest:
        cycle_start_date = latest.end_date

        # add one month to end date (make sure accurate number of days)
        cycle_end_date = latest.end_date + relativedelta(months=1)

        # set context values
        context["cycle_start_date"] = cycle_start_date.strftime("%Y-%m-%d")
        context["cycle_end_date"] = cycle_end_date.strftime("%Y-%m-%d")
        context["previous_total"] = latest.previous_total
        context["previous_usage"] = latest.previous_usage
        context["current_total"] = latest.current_total
        context["current_usage"] = latest.current_usage
        context["apply_fix_rate"] = latest.apply_fix_rate
        context["fix_rate"] = fix_rate
        context["h2o_usage_cost_threshold"] = threshold
        context["stored_fix_rate"] = latest.stored_fix_rate
        context["stored_maintenance_fee"] = latest.stored_maintenance_fee
        context["stored_cost_per_h2o_usage"] = latest.stored_cost_per_h2o_usage
        context["maintenance_fee"] = latest.maintenance_fee
        context["cost_per_h2o_usage"] = latest.cost_per_h2o_usage
        context["maintenance_fee_note"] = latest.maintenance_fee_note

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
        tenant_group = TenantGroup.objects.get(id=tenant_group_id)
        config = tenant_group.space.property.configuration
        billing_type = config.billing_type
    except TenantGroup.DoesNotExist:
        return HttpResponse(status=404)

    try:
        page_number = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page_number = 1

    if billing_type == "electricity":
        billings = ElectricityConsumptionRecord.objects.filter(
            tenant_group_id=tenant_group_id
        ).order_by("-created_at")
    else:
        billings = WaterConsumptionRecord.objects.filter(
            tenant_group_id=tenant_group_id
        ).order_by("-created_at")

    paginator = Paginator(billings, 3)
    page_obj = paginator.get_page(page_number)
    context = {
        "billings": page_obj,
        "billing_type": billing_type,
        "page_obj": page_obj,
        "tenant_group_id": tenant_group_id,
        "open_modal": True
    }
    # Return the full modal only when opening it (target is the modal itself);
    # tab switches and infinite scroll target inner elements and get rows only.
    if request.htmx and request.htmx.target == "billingHistoryModal":
        template = "properties/partials/billing_history_modal.html"
    else:
        template = "properties/partials/billing_history_rows.html"
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
        if config.billing_type != 'water':
            continue

        config_maintenance_fee = config.maintenance_fee
        config_fix_rate = config.water_billing_fix_rate
        config_h2o_usage_cost_threshold = config.h2o_usage_cost_threshold
        config_cost_per_h2o_usage = config.cost_per_h2o_usage

        # get latest recorded water billing for this tenant group
        start_date = ""
        end_date = ""
        previous_usage = 0
        current_usage = 0
        apply_fix_rate = True
        fix_rate = config_fix_rate
        h2o_usage_cost_threshold = config_h2o_usage_cost_threshold
        cost_per_h2o_usage = config_cost_per_h2o_usage
        maintenance_fee = config_maintenance_fee
        maintenance_fee_note = ""

        latest_billing = tenant_group.water_consumption_records.order_by('-created_at').first()
        if latest_billing:
            start_date = latest_billing.end_date.strftime("%Y-%m-%d")
            end_date = (latest_billing.end_date + relativedelta(months=1)).strftime("%Y-%m-%d")
            previous_usage = latest_billing.previous_usage
            current_usage = latest_billing.current_usage

        data.append({
            'tenant_group_id': str(tenant_group.id),
            'tenant_group_name': tenant_group.name,
            'property_and_space': property_and_space,
            'start_date': start_date,
            'end_date': end_date,
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


def import_billings(request, *args, **kwargs):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
    
        try:
            file_name = uploaded_file.name.lower()
            if file_name.startswith('water_billing'):
                import_water_billings(uploaded_file)
            elif file_name.startswith('electricity_billing'):
                import_electricity_billings(uploaded_file)
            else:
                response = HttpResponse(status=200)
                response["HX-Trigger"] = json.dumps({
                    "toast": {
                        "type": "error", 
                        "message": "Invalid file name. File must start with 'water_billing' or 'electricity_billing'."
                    }
                })
                return response

        except BillingImportError as e:
            response = HttpResponse(status=200)
            response["HX-Trigger"] = json.dumps({
                "toast": {"type": "error", "message": str(e)}
            })
            return response


        response = HttpResponse(status=200)
        response["HX-Trigger"] = json.dumps({
            "toast": {"type": "success", "message": "Billing imported successfully."}
        })
        return response
    
    response = HttpResponse(status=200)
    response["HX-Trigger"] = json.dumps({
        "toast": {"type": "error", "message": "No file uploaded."}
    })
    return response


def get_group_latest_electricitybilling(request, tenant_group_id):
    try:
        tenant_group = TenantGroup.objects.get(id=tenant_group_id)
        config = tenant_group.space.property.configuration
        head_count = tenant_group.tenants.count()
        cost_per_electricity_usage = config.cost_per_electricity_usage
        common_usage_per_head = config.common_usage_per_head 
        fixed_water_fee = config.fixed_water_fee
    except TenantGroup.DoesNotExist:
        return HttpResponse(status=404)

    electricity_consumptions = ElectricityConsumptionRecord.objects.filter(
        tenant_group=tenant_group
    ).order_by('-created_at')[:1]

    latest = None if not electricity_consumptions.count() else electricity_consumptions[0]

    context = {
        "previous_total": 0,
        "previous_usage": 0,
        "current_total": 0,
        "head_count": head_count,
        "current_usage": 0,
        "common_usage_per_head": common_usage_per_head,
        "stored_head_count": 0,
        "cost_per_electricity_usage": cost_per_electricity_usage,
        "stored_cost_per_electricity_usage": 0,
        "fixed_water_fee": fixed_water_fee,
        "open_modal": True,
    }

    # determine cycle start and end dates
    cycle_start_date = None
    cycle_end_date = None
    if latest:
        cycle_start_date = latest.end_date

        # add one month to end date (make sure accurate number of days)
        cycle_end_date = latest.end_date + relativedelta(months=1)

        # set remaining context values
        context["cycle_start_date"] = cycle_start_date.strftime("%Y-%m-%d")
        context["cycle_end_date"] = cycle_end_date.strftime("%Y-%m-%d")
        context["previous_total"] = latest.previous_total
        context["previous_usage"] = latest.previous_usage
        context["current_total"] = latest.current_total
        context["current_usage"] = latest.current_usage
        context["stored_cost_per_electricity_usage"] = latest.stored_cost_per_electricity_usage
        context["stored_common_usage_per_head"] = latest.stored_common_usage_per_head
        context["stored_head_count"] = latest.stored_head_count
        context["multiply_by_head_count"] = latest.stored_multiply_by_head_count

    if request.htmx:
        return render(
            request, "properties/partials/electricity_billing_modal.html", 
            context
        )

    return HttpResponse(status=400)


def detail_electricity_billing(request, pk, *args, **kwargs):
    if request.method == "GET":
        # Handle GET request
        electricity_consumption = ElectricityConsumptionRecord.objects.get(pk=pk)
        context = {
            "electricity_consumption": electricity_consumption
        }
        return render(
            request, "billings/electricity_billing_detail.html",
            context
        )
    return HttpResponse(status=400)


def _latest_invoices_for_billing_type(billing_type):
    """
    Return the latest consumption record for every active tenant group whose
    configured billing type matches `billing_type` (skipping groups with no
    record yet). Used to bulk-render invoice images.
    """
    invoices = []
    tenant_groups = TenantGroup.objects.filter(is_active=True)
    for tenant_group in tenant_groups:
        try:
            if tenant_group.billing_type != billing_type:
                continue
        except AttributeError:
            # Tenant group without a property configuration; skip it.
            continue

        if billing_type == "electricity":
            record = tenant_group.electricity_consumption_records.order_by("-end_date").first()
        else:
            record = tenant_group.water_consumption_records.order_by("-created_at").first()

        if record:
            invoices.append(record)
    return invoices


def download_water_invoices(request, *args, **kwargs):
    if request.method != "GET":
        return HttpResponse(status=400)
    return render(request, "billings/bulk_invoices.html", {
        "invoices": _latest_invoices_for_billing_type("water"),
        "billing_type": "water",
        "title": "Download Water Invoices",
        "zip_filename": "water-invoices.zip",
    })


def download_electricity_invoices(request, *args, **kwargs):
    if request.method != "GET":
        return HttpResponse(status=400)
    return render(request, "billings/bulk_invoices.html", {
        "invoices": _latest_invoices_for_billing_type("electricity"),
        "billing_type": "electricity",
        "title": "Download Electricity Invoices",
        "zip_filename": "electricity-invoices.zip",
    })


def create_electricity_billing(request, *args, **kwargs):
    if request.method != "POST":
        return HttpResponse(status=405)
    
    tenant_group = TenantGroup.objects.filter(
        pk=request.POST.get("tenant_group_id")
    ).first()
    if tenant_group is None:
        return HttpResponse(status=400)

    form = ElectricityConsumptionRecordForm(request.POST)
    if not form.is_valid():
        context = _electricity_billing_modal_context(request.POST, form)
        response = render(
            request, "properties/partials/electricity_billing_modal.html", context, 
            status=400
        )
        response["HX-Trigger"] = json.dumps({
            "toast": {"type": "error", "message": "Please correct the highlighted fields."}
        })
        return response

    record = form.save(commit=False)
    record.tenant_group = tenant_group

    # Recompute final bill server-side
    electricity_usage_diff = record.current_usage - record.previous_usage
    cost_per_electricity_usage = record.stored_cost_per_electricity_usage or 0
    common_usage_per_head = record.stored_common_usage_per_head or 0
    head_count = record.stored_head_count or 0
    fixed_water_fee = record.stored_fixed_water_fee or 0
    multiply_by_head_count = record.stored_multiply_by_head_count

    # Calculate final bill
    final_bill = (
        (electricity_usage_diff * cost_per_electricity_usage) 
        + (common_usage_per_head * head_count if multiply_by_head_count else common_usage_per_head)
        + (fixed_water_fee * head_count if multiply_by_head_count else fixed_water_fee)
    )
    record.stored_final_bill = final_bill

    record.save()
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"type": "success", "message": "Electricity billing created successfully."}
    })
    return response


def download_electricity_billings_template(request, *args, **kwargs):
    if request.method != 'GET':
        return HttpResponse(status=400)
    
    tenant_groups = TenantGroup.objects.filter(is_active=True)
    
    # downloadable excel file with following rows:
    # tenant_group_id, tenant_group_name, property_and_space, 
    # start_date, end_date, previous_usage, current_usage, 
    # multiply_by_head_count, head_count, cost_per_electricity_usage, 
    # common_usage_per_head, fixed_water_fee
    columns = [
        'tenant_group_id', 'tenant_group_name', 'property_and_space',
        'start_date', 'end_date', 'previous_usage', 'current_usage',
        'multiply_by_head_count', 'head_count', 'cost_per_electricity_usage', 
        'common_usage_per_head', 'fixed_water_fee'
    ]

    placeholder_row = {
        'tenant_group_id': '(Do not edit)',
        'tenant_group_name': '(Do not edit)',
        'property_and_space': '(Do not edit)',
        'start_date': 'YYYY-MM-DD (e.g. 2025-10-01)',
        'end_date': 'YYYY-MM-DD (e.g. 2025-10-31)',
        'previous_usage': '50',
        'current_usage': '55',
        'multiply_by_head_count': 'TRUE/FALSE',
        'head_count': '2',
        'cost_per_electricity_usage': '20',
        'common_usage_per_head': '300',
        'fixed_water_fee': '300'
    }

    data = [placeholder_row]
    for tenant_group in tenant_groups:
        space = tenant_group.space
        property = space.property
        property_and_space = f"{property.name} - {space.name}"
        
        config = property.configuration
        if config.billing_type != 'electricity':
            continue
        cost_per_electricity_usage = config.cost_per_electricity_usage
        common_usage_per_head = config.common_usage_per_head
        fixed_water_fee = config.fixed_water_fee
        head_count = tenant_group.tenants.count()

        latest_billing = tenant_group.electricity_consumption_records.order_by('-end_date').first()
        start_date = latest_billing.end_date.strftime("%Y-%m-%d")
        end_date = (latest_billing.end_date + relativedelta(months=1)).strftime("%Y-%m-%d")
        previous_usage = latest_billing.previous_usage
        current_usage = latest_billing.current_usage
        multiply_by_head_count = True

        data.append({
            'tenant_group_id': tenant_group.id,
            'tenant_group_name': tenant_group.name,
            'property_and_space': property_and_space,
            'start_date': start_date,
            'end_date': end_date,
            'previous_usage': previous_usage,
            'current_usage': current_usage,
            'multiply_by_head_count': multiply_by_head_count,
            'head_count': head_count,
            'cost_per_electricity_usage': cost_per_electricity_usage,
            'common_usage_per_head': common_usage_per_head,
            'fixed_water_fee': fixed_water_fee
        })

    df = pd.DataFrame(data)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="electricity_billings_template.xlsx"'
    df.to_excel(response, index=False, engine='openpyxl')

    return response