from django.contrib import admin
from .models import Property, PropertyConfig, Space, TenantGroup, Tenant

# Register your models here.
admin.site.register(Property)
admin.site.register(PropertyConfig)
admin.site.register(Space)
admin.site.register(TenantGroup)
admin.site.register(Tenant)
