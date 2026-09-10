from django.shortcuts import get_object_or_404, render

from .models import Vehicle


def _build_vehicle_panel_context(vehicle):
    trips = list(vehicle.trips.prefetch_related("points")[:10])
    grouped_routes = {}
    for trip in trips:
        points = list(trip.points.all())
        if len(points) < 2:
            continue
        route_key = (
            round(float(points[0].latitude), 3),
            round(float(points[0].longitude), 3),
            round(float(points[-1].latitude), 3),
            round(float(points[-1].longitude), 3),
        )
        grouped_routes.setdefault(route_key, {"count": 0, "path": []})
        grouped_routes[route_key]["count"] += 1
        grouped_routes[route_key]["path"] = [
            [float(point.latitude), float(point.longitude)] for point in points
        ]

    frequent_routes = [
        {"count": route["count"], "path": route["path"]}
        for route in sorted(
            grouped_routes.values(),
            key=lambda entry: entry["count"],
            reverse=True,
        )
    ]

    return {
        "vehicle": vehicle,
        "trips": trips,
        "latest_soc_snapshot": vehicle.snapshots.exclude(soc_kwh__isnull=True).first(),
        "latest_odometer_snapshot": vehicle.snapshots.exclude(
            odometer_miles__isnull=True
        ).first(),
        "frequent_routes": frequent_routes[:5],
    }


def index(request):
    vehicles = Vehicle.objects.all()
    selected_vehicle = vehicles.first()
    context = {
        "vehicles": vehicles,
        "selected_vehicle_panel": (
            _build_vehicle_panel_context(selected_vehicle)
            if selected_vehicle is not None
            else None
        ),
    }
    return render(request, "dashboard/index.html", context)


def vehicle_panel(request, pk):
    vehicle = get_object_or_404(Vehicle.objects.prefetch_related("trips__points", "snapshots"), pk=pk)
    return render(
        request,
        "dashboard/_vehicle_panel.html",
        _build_vehicle_panel_context(vehicle),
    )
