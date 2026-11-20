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
        'download-water-billings-template',
        views.download_water_billings_template,
        name="download_water_billings_template"
    ),
    path(
        'download-electricity-billings-template',
        views.download_electricity_billings_template,
        name="download_electricity_billings_template"
    ),
    path(
        '<int:tenant_group_id>/latest-electricity-billing',
        views.get_group_latest_electricitybilling,
        name="latest_electricitybilling"
    ),
    path(
        'create-electricity-billing',
        views.create_electricity_billing,
        name="create_electricity_billing"
    ),
    path(
        '<uuid:pk>/electricity-billing-detail',
        views.detail_electricity_billing,
        name="electricity_billing_detail"
    ),
    path(
        'import-billings',
        views.import_billings,
        name="import_billings"
    ),]
