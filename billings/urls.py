from django.urls import path

from . import views

urlpatterns = [
    path(
        '<int:tenant_group_id>/list-billings',
        views.get_billing_history,
        name="billing_history"
    ),
    path(
        '<int:tenant_group_id>/latest-water-billing',
        views.get_group_latest_waterbilling,
        name="latest_waterbilling"
    ),
    path(
        '<uuid:pk>/water-billing-detail',
        views.detail_water_billing,
        name="water_billing_detail"
    ),
    path(
        'create-water-billing',
        views.create_water_billing,
        name="create_water_billing"
    ),
    path(
        'import-water-billings',
        views.import_water_billings,
        name="import_water_billings"
    ),
    path(
        'download-water-billings-template',
        views.download_water_billings_template,
        name="download_water_billings_template"
    ),
]