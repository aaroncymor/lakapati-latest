import uuid
from django.db import models
from properties.models import TenantGroup


# Create your models here.
class WaterConsumptionRecord(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    tenant_group = models.ForeignKey(
        TenantGroup,
        on_delete=models.CASCADE,
        related_name="water_consumption_records"
    )
    previous_total = models.IntegerField()
    current_total = models.IntegerField()
    previous_usage = models.IntegerField()
    current_usage = models.IntegerField()
    stored_maintenance_fee = models.IntegerField()
    stored_cost_per_h2o_usage = models.IntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def water_usage_diff(self):
        return self.current_usage - self.previous_usage

    @property
    def total_water_usage_diff(self):
        return self.current_total - self.previous_total

    @property
    def cost_per_h2o_usage(self):
        config = self.tenant_group.space.property.configuration
        return config.cost_per_h2o_usage

    @property
    def maintenance_fee(self):
        config = self.tenant_group.space.property.configuration
        return config.maintenance_fee

    @property
    def final_bill(self):
        config = self.tenant_group.space.property.configuration
        cost_per_h2o_usage = config.cost_per_h2o_usage
        maintenance_fee = config.maintenance_fee
        water_usage_diff = self.current_total - self.previous_total
        return (water_usage_diff * cost_per_h2o_usage) + maintenance_fee


    class Meta:
        verbose_name_plural = "Water Consumption Records"
