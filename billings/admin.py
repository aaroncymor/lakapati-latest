from django.contrib import admin

from .models import WaterConsumptionRecord, ElectricityConsumptionRecord


# Register your models here.
admin.site.register(WaterConsumptionRecord)
admin.site.register(ElectricityConsumptionRecord)
