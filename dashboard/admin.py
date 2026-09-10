from django.contrib import admin

from .models import Trip, TripPoint, Vehicle, VehicleSnapshot


class TripPointInline(admin.TabularInline):
    model = TripPoint
    extra = 0


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("vin", "name", "reference_battery_capacity_kwh")
    search_fields = ("vin", "name")


@admin.register(VehicleSnapshot)
class VehicleSnapshotAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "recorded_at", "odometer_miles", "soc_kwh", "total_battery_capacity_kwh")
    list_filter = ("vehicle",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "source_trip_id", "started_at", "ended_at", "distance_miles", "efficiency_mi_per_kwh")
    list_filter = ("vehicle",)
    inlines = [TripPointInline]
