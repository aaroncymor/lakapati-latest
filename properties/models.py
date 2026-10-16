from django.db import models


# Create your models here.

class Property(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self, *args, **kwargs):
        return self.name

    class Meta:
        verbose_name_plural = "Properties"


class PropertyConfig(models.Model):
    property = models.OneToOneField(
        Property,
        on_delete=models.CASCADE,
        related_name="configuration"
    )
    cost_per_h2o_usage = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    maintenance_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    water_billing_fix_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    h2o_usage_cost_threshold = models.IntegerField(default=0)

    def __str__(self, *args, **kwargs):
        return f"{self.property.name} Config"


SPACE_STATUS_CHOICES = (
    ('vacant', 'Vacant'),
    ('occupied', 'Occupied')
)


class Space(models.Model):
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="spaces"
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=8, choices=SPACE_STATUS_CHOICES, default='occupied'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self, *args, **kwargs):
        return self.name


class TenantGroup(models.Model):
    space = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="tenant_groups"
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    primary = models.ForeignKey(
        "Tenant", on_delete=models.CASCADE, null=True, blank=True
    )
    monthly_rent = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    security_deposit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    first_month_advance = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    second_month_advance = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self, *args, **kwargs):
        return self.name

    class Meta:
        verbose_name_plural = "Tenant Groups"

    @property
    def has_multiple_tenants(self):
        return self.tenants.count() > 1


class Tenant(models.Model):
    group = models.ForeignKey(
        TenantGroup, on_delete=models.CASCADE, related_name="tenants"
    )
    first_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    email = models.EmailField(max_length=254, null=True, blank=True)
    mobile = models.CharField(max_length=12, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self, *args, **kwargs):
        return f"{self.first_name } {self.last_name}"

    @property
    def is_primary(self):
        return self.group.primary == self
