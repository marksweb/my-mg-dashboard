from django.db import models

KM_TO_MI = 0.621371


class Vehicle(models.Model):
    vin = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100, blank=True)
    reference_battery_capacity_kwh = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Nominal usable battery capacity for degradation tracking.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "vin"]

    def __str__(self):
        return self.name or self.vin

    @property
    def latest_battery_health_percent(self):
        if not self.reference_battery_capacity_kwh:
            return None
        latest_snapshot = self.snapshots.exclude(total_battery_capacity_kwh__isnull=True).order_by("-recorded_at").first()
        if not latest_snapshot or latest_snapshot.total_battery_capacity_kwh is None:
            return None
        return round(
            float(latest_snapshot.total_battery_capacity_kwh / self.reference_battery_capacity_kwh) * 100,
            2,
        )


class VehicleSnapshot(models.Model):
    vehicle = models.ForeignKey(Vehicle, related_name="snapshots", on_delete=models.CASCADE)
    recorded_at = models.DateTimeField()
    odometer_miles = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    soc_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    total_battery_capacity_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]


class Trip(models.Model):
    vehicle = models.ForeignKey(Vehicle, related_name="trips", on_delete=models.CASCADE)
    source_trip_id = models.CharField(max_length=64, null=True, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    distance_miles = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    start_soc_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    end_soc_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    battery_capacity_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle", "source_trip_id"],
                condition=models.Q(source_trip_id__isnull=False),
                name="unique_trip_id_per_vehicle",
            )
        ]

    def __str__(self):
        return f"{self.vehicle} trip {self.source_trip_id or self.pk}"

    @property
    def efficiency_mi_per_kwh(self):
        if self.start_soc_kwh is None or self.end_soc_kwh is None:
            return None
        energy_used = float(self.start_soc_kwh) - float(self.end_soc_kwh)
        if energy_used <= 0:
            return None
        return round(float(self.distance_miles) / energy_used, 2)


class TripPoint(models.Model):
    trip = models.ForeignKey(Trip, related_name="points", on_delete=models.CASCADE)
    recorded_at = models.DateTimeField()
    sequence = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    altitude_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["sequence", "id"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "sequence"], name="unique_trip_point_sequence")
        ]
