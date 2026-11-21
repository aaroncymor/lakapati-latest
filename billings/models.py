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
    previous_total = models.DecimalField(max_digits=10, decimal_places=2)
    current_total = models.DecimalField(max_digits=10, decimal_places=2)
    previous_usage = models.DecimalField(max_digits=10, decimal_places=2)
    current_usage = models.DecimalField(max_digits=10, decimal_places=2)
    stored_maintenance_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    maintenance_fee_note = models.CharField(max_length=255, null=True, blank=True)
    apply_fix_rate = models.BooleanField(default=True)
    stored_fix_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stored_h2o_usage_cost_threshold = models.IntegerField(null=True, blank=True)
    stored_cost_per_h2o_usage = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stored_final_bill = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_fix_rate_applicable(self):
        usage_diff = self.current_usage - self.previous_usage
        return (
            self.apply_fix_rate and
            usage_diff <= self.stored_h2o_usage_cost_threshold
        )

    @property
    def water_usage_diff(self):
        return self.current_usage - self.previous_usage

    @property
    def total_water_usage_diff(self):
        return self.current_total - self.previous_total

    @property
    def cost_per_h2o_usage(self):
        if self.stored_cost_per_h2o_usage:
            return self.stored_cost_per_h2o_usage

        config = self.tenant_group.space.property.configuration
        return config.cost_per_h2o_usage

    @property
    def maintenance_fee(self):
        if self.stored_maintenance_fee:
            return self.stored_maintenance_fee
        
        config = self.tenant_group.space.property.configuration
        return config.maintenance_fee

    @property
    def final_bill(self):
        if self.stored_final_bill:
            return self.stored_final_bill
        
        config = self.tenant_group.space.property.configuration
        cost_per_h2o_usage = config.cost_per_h2o_usage
        maintenance_fee = config.maintenance_fee
        water_usage_diff = self.current_usage - self.previous_usage
        
        if self.apply_fix_rate:
            fix_rate = config.water_billing_fix_rate
            if water_usage_diff > config.h2o_usage_cost_threshold:
                return fix_rate + maintenance_fee
        
        # if high usage, apply maintenance fee + cost per h2o usage
        return (water_usage_diff * cost_per_h2o_usage) + maintenance_fee

    @property
    def calculated_cost_per_water_usage(self):
        usage_diff = self.current_usage - self.previous_usage
        if (
            self.stored_fix_rate 
            and self.apply_fix_rate
            and usage_diff <= self.stored_h2o_usage_cost_threshold
        ):
            return self.stored_fix_rate

        return (self.stored_cost_per_h2o_usage * usage_diff)

    class Meta:
        verbose_name_plural = "Water Consumption Records"


class ElectricityConsumptionRecord(models.Model):
    """
    Electricity bill
    Applied to some properties (e.g., Amihan)
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    tenant_group = models.ForeignKey(
        TenantGroup,
        on_delete=models.CASCADE,
        related_name="electricity_consumption_records"
    )
    previous_total = models.DecimalField(max_digits=10, decimal_places=2)
    current_total = models.DecimalField(max_digits=10, decimal_places=2)
    previous_usage = models.DecimalField(max_digits=10, decimal_places=2)
    current_usage = models.DecimalField(max_digits=10, decimal_places=2)
    stored_head_count = models.IntegerField(default=0)
    stored_multiply_by_head_count = models.BooleanField(default=True)
    stored_cost_per_electricity_usage = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    stored_common_usage_per_head = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    stored_fixed_water_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    stored_final_bill = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def electricity_usage_diff(self):
        return self.current_usage - self.previous_usage

    @property
    def total_electricity_usage_diff(self):
        return self.current_total - self.previous_total

    @property
    def calculated_cost_per_electricity_usage(self):
        usage_diff = self.current_usage - self.previous_usage
        if self.stored_cost_per_electricity_usage > 0:
            return self.stored_cost_per_electricity_usage * usage_diff
        
        config = self.tenant_group.space.property.configuration
        return config.cost_per_electricity_usage * usage_diff
    
    @property
    def common_usage_per_head(self):
        if self.stored_common_usage_per_head > 0:
            return self.stored_common_usage_per_head
        
        config = self.tenant_group.space.property.configuration
        return config.common_usage_per_head
    
    @property
    def calculated_common_usage_per_head(self):
        # already calculated and stored
        common_usage = 0
        multiply_by_head_count = True
        head_count = 0
        if self.stored_common_usage_per_head > 0:
            common_usage = self.stored_common_usage_per_head
            multiply_by_head_count = self.stored_multiply_by_head_count
            head_count = self.stored_head_count
        else:
            config = self.tenant_group.space.property.configuration
            common_usage = config.common_usage_per_head
            head_count = self.tenant_group.tenants.count()
        
        if multiply_by_head_count:
            if head_count == 0:
                return 0
            return common_usage * head_count
        
        # not multiplied by head count
        return common_usage
    
    @property
    def fixed_water_fee(self):
        if self.stored_fixed_water_fee > 0:
            return self.stored_fixed_water_fee
        
        config = self.tenant_group.space.property.configuration
        return config.fixed_water_fee
    
    
    @property
    def calculated_fixed_water_fee(self):
        # already calculated and stored
        fixed_water_fee = 0
        multiply_by_head_count = True
        head_count = 0
        if self.stored_fixed_water_fee > 0:
            fixed_water_fee = self.stored_fixed_water_fee
            multiply_by_head_count = self.stored_multiply_by_head_count
            head_count = self.stored_head_count
        else:
            config = self.tenant_group.space.property.configuration
            fixed_water_fee = config.fixed_water_fee
            head_count = self.tenant_group.tenants.count()

        if multiply_by_head_count:
            return fixed_water_fee * head_count
        
        # not multiplied by head count
        return fixed_water_fee
    
    @property
    def final_bill(self):
        # already calculated and stored
        if self.stored_final_bill > 0:
            return self.stored_final_bill

        multiply_by_head_count = True
        head_count = self.tenant_group.tenants.count()
        
        # calculate final bill
        electricity_usage_diff = self.current_usage - self.previous_usage

        final_bill = (
            (electricity_usage_diff * self.cost_per_electricity_usage) 
            + (self.common_usage_per_head * head_count if multiply_by_head_count else self.common_usage_per_head)
            + (self.fixed_water_fee * head_count if multiply_by_head_count else self.fixed_water_fee)
        )
        return final_bill
        
    