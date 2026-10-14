from django.urls import path
from . import views


urlpatterns = [
    path('', views.list_tenant_groups, name="tenant_groups_list"),
]
