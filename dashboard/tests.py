from datetime import timedelta
from decimal import Decimal
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Trip, TripPoint, Vehicle, VehicleSnapshot, VehicleStatus
from .services.mqtt import ParsedTopic, SaicMqttIngestor, parse_vehicle_topic


class MqttIngestorTests(TestCase):
    def test_parse_vehicle_topic_requires_vehicle_suffix(self):
        self.assertEqual(
            parse_vehicle_topic("saic/joe@example.com/vehicles/LSJ123/location/position"),
            ParsedTopic(vin="LSJ123", suffix="location/position"),
        )
        self.assertIsNone(parse_vehicle_topic("saic/account/lastLogin"))

    def test_parse_vehicle_topic_without_account_segment(self):
        self.assertEqual(
            parse_vehicle_topic("saic/vehicles/LSJ123/drivetrain/soc_kwh"),
            ParsedTopic(vin="LSJ123", suffix="drivetrain/soc_kwh"),
        )

    def test_ingest_trip_and_points_updates_efficiency(self):
        ingestor = SaicMqttIngestor()
        recorded_at = timezone.now()

        ingestor.ingest("saic/joe@example.com/vehicles/LSJ123/drivetrain/soc_kwh", "45.5", recorded_at=recorded_at)
        ingestor.ingest(
            "saic/joe@example.com/vehicles/LSJ123/drivetrain/currentJourney",
            json.dumps({"id": 77, "distance": 12.0}),
            recorded_at=recorded_at + timedelta(minutes=5),
        )
        ingestor.ingest(
            "saic/joe@example.com/vehicles/LSJ123/location/position",
            json.dumps({"latitude": 51.5007, "longitude": -0.1246}),
            recorded_at=recorded_at + timedelta(minutes=6),
        )
        ingestor.ingest(
            "saic/joe@example.com/vehicles/LSJ123/location/position",
            json.dumps({"latitude": 51.5010, "longitude": -0.1416}),
            recorded_at=recorded_at + timedelta(minutes=12),
        )
        ingestor.ingest("saic/joe@example.com/vehicles/LSJ123/drivetrain/soc_kwh", "41.5", recorded_at=recorded_at + timedelta(minutes=15))

        trip = Trip.objects.get(source_trip_id="77")
        self.assertEqual(trip.points.count(), 2)
        self.assertEqual(trip.start_soc_kwh, Decimal("45.5"))
        self.assertEqual(trip.end_soc_kwh, Decimal("41.5"))
        self.assertAlmostEqual(trip.efficiency_mi_per_kwh, 1.86, places=2)

    def test_ingest_capacity_creates_history_for_degradation_tracking(self):
        ingestor = SaicMqttIngestor()
        vehicle = Vehicle.objects.create(vin="LSJ456", reference_battery_capacity_kwh=Decimal("51.00"))

        ingestor.ingest("saic/joe@example.com/vehicles/LSJ456/drivetrain/totalBatteryCapacity", "48.45")

        vehicle.refresh_from_db()
        self.assertEqual(VehicleSnapshot.objects.get(vehicle=vehicle).total_battery_capacity_kwh, Decimal("48.45"))
        self.assertEqual(vehicle.latest_battery_health_percent, 95.0)

    def test_ingest_door_and_window_state(self):
        ingestor = SaicMqttIngestor()

        ingestor.ingest("saic/joe@example.com/vehicles/LSJ999/doors/locked", "true")
        ingestor.ingest("saic/joe@example.com/vehicles/LSJ999/windows/driver", "true")
        ingestor.ingest("saic/joe@example.com/vehicles/LSJ999/windows/passenger", "false")
        ingestor.ingest("saic/joe@example.com/vehicles/LSJ999/doors/boot", "false")

        status = VehicleStatus.objects.get(vehicle__vin="LSJ999")
        self.assertTrue(status.doors_locked)
        self.assertTrue(status.window_driver)
        self.assertFalse(status.window_passenger)
        self.assertFalse(status.door_boot)
        self.assertTrue(status.any_window_open)
        self.assertFalse(status.any_door_open)
        self.assertIsNotNone(status.status_updated_at)

    def test_ingest_position_stores_heading_and_speed(self):
        ingestor = SaicMqttIngestor()
        recorded_at = timezone.now()

        ingestor.ingest(
            "saic/joe@example.com/vehicles/LSJ321/location/position",
            json.dumps({"latitude": 51.5, "longitude": -0.12, "heading": 90, "speed": 42.5}),
            recorded_at=recorded_at,
        )

        point = TripPoint.objects.get(trip__vehicle__vin="LSJ321")
        self.assertEqual(point.heading, Decimal("90"))
        self.assertEqual(point.speed_kph, Decimal("42.5"))

    def test_ingest_standalone_heading_updates_latest_point(self):
        ingestor = SaicMqttIngestor()
        now = timezone.now()

        ingestor.ingest(
            "saic/joe@example.com/vehicles/LSJ654/location/position",
            json.dumps({"latitude": 51.5, "longitude": -0.12}),
            recorded_at=now,
        )
        ingestor.ingest("saic/joe@example.com/vehicles/LSJ654/location/heading", "180")
        ingestor.ingest("saic/joe@example.com/vehicles/LSJ654/location/speed", "30")

        point = TripPoint.objects.get(trip__vehicle__vin="LSJ654")
        self.assertEqual(point.heading, Decimal("180"))
        self.assertEqual(point.speed_kph, Decimal("30"))


class DashboardViewTests(TestCase):
    def test_vehicle_panel_renders_trip_table_and_map_target(self):
        vehicle = Vehicle.objects.create(vin="LSJ789", name="MG ZS")
        trip = Trip.objects.create(
            vehicle=vehicle,
            source_trip_id="88",
            started_at=timezone.now() - timedelta(hours=1),
            ended_at=timezone.now(),
            distance_miles=Decimal("12.40"),
            start_soc_kwh=Decimal("40.0"),
            end_soc_kwh=Decimal("36.0"),
        )
        TripPoint.objects.create(trip=trip, recorded_at=timezone.now(), sequence=1, latitude=Decimal("51.500700"), longitude=Decimal("-0.124600"))
        TripPoint.objects.create(trip=trip, recorded_at=timezone.now(), sequence=2, latitude=Decimal("51.501000"), longitude=Decimal("-0.141600"))

        response = self.client.get(reverse("vehicle-panel", args=[vehicle.pk]))

        self.assertContains(response, "Recent trips")
        self.assertContains(response, "mi/kWh")
        self.assertContains(response, f"route-map-{vehicle.pk}")

    def test_index_page_uses_htmx_buttons(self):
        vehicle = Vehicle.objects.create(vin="LSJ101", name="MG ZS EV")

        response = self.client.get(reverse("dashboard-index"))

        self.assertContains(response, "htmx.org")
        self.assertContains(response, reverse("vehicle-panel", args=[vehicle.pk]))

    def test_vehicle_panel_shows_window_open_warning(self):
        vehicle = Vehicle.objects.create(vin="LSJ202", name="MG4")
        VehicleStatus.objects.create(
            vehicle=vehicle,
            doors_locked=True,
            window_driver=True,
            door_boot=False,
            status_updated_at=timezone.now(),
        )

        response = self.client.get(reverse("vehicle-panel", args=[vehicle.pk]))

        self.assertContains(response, "Security &amp; closures")
        self.assertContains(response, "Window open")
        self.assertContains(response, "Locked")
