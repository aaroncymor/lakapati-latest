from django.http import HttpResponse
from django.shortcuts import render
from django.db.models import Q
from django.core.paginator import Paginator
from .models import TenantGroup


# Create your views here.
def list_tenant_groups(request, *args, **kwargs):

    keyword = request.GET.get('q', '').strip()

    try:
        page_num = int(request.GET.get('page', 1))
        show = int(request.GET('show', 25))
    except (ValueError, TypeError):
        page_num = 1
        show = 25

    tenant_groups = TenantGroup.objects.filter(is_active=True)
    if len(keyword) > 0:
        tenant_groups = tenant_groups.filter(
            (
                Q(name__icontains=keyword) |
                (Q(space__name__icontains=keyword) & Q(space__is_active=True)) |
                (
                    Q(space__property__name__icontains=keyword) &
                    Q(space__property__is_active=True)
                ) |
                (
                    Q(primary__is_active=True) &
                    Q(primary__first_name__icontains=keyword) |
                    Q(primary__middle_name__icontains=keyword) |
                    Q(primary__email=keyword) |
                    Q(primary__mobile=keyword) |
                    Q(primary__last_name__icontains=keyword)
                )
            )
        )

    tenant_groups = tenant_groups.order_by("-created_at")
    paginator = Paginator(tenant_groups, show)
    page_obj = paginator.get_page(page_num)
    context = {
        "tenant_groups": page_obj,
        "page_obj": page_obj
    }

    if request.htmx:
        return render(request, 'properties/partials/table.html', context)

    return render(request, 'properties/dashboard.html', context)