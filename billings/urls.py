from django.urls import path

from . import views

urlpatterns = [
    path(
        '<int:tenant_group_id>/latest-water-billing',
        views.get_group_latest_waterbilling,
        name="latest_waterbilling"
    )
]
