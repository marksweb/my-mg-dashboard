import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from dashboard.models import KM_TO_MI, Trip, TripPoint, Vehicle, VehicleSnapshot


@dataclass(frozen=True)
class ParsedTopic:
    vin: str
    suffix: str


def parse_vehicle_topic(topic, topic_prefix="saic"):
    prefix = f"{topic_prefix}/vehicles/"
    if not topic.startswith(prefix):
        return None
    remainder = topic[len(prefix):]
    vin, separator, suffix = remainder.partition("/")
    if not separator or not vin or not suffix:
        return None
    return ParsedTopic(vin=vin, suffix=suffix)


class SaicMqttIngestor:
    def __init__(self, topic_prefix="saic"):
        self.topic_prefix = topic_prefix

    def ingest(self, topic, payload, recorded_at=None):
        parsed_topic = parse_vehicle_topic(topic, self.topic_prefix)
        if not parsed_topic:
            return None

        vehicle, _ = Vehicle.objects.get_or_create(vin=parsed_topic.vin)
        recorded_at = recorded_at or timezone.now()

        if parsed_topic.suffix == "drivetrain/currentJourney":
            return self._handle_current_journey(vehicle, payload, recorded_at)
        if parsed_topic.suffix == "location/position":
            return self._handle_location(vehicle, payload, recorded_at)
        if parsed_topic.suffix == "drivetrain/soc_kwh":
            return self._handle_soc(vehicle, payload, recorded_at)
        if parsed_topic.suffix == "drivetrain/totalBatteryCapacity":
            return self._handle_capacity(vehicle, payload, recorded_at)
        if parsed_topic.suffix == "drivetrain/mileage":
            return self._handle_mileage(vehicle, payload, recorded_at)
        return None

    def _handle_current_journey(self, vehicle, payload, recorded_at):
        data = self._parse_json_payload(payload)
        if not isinstance(data, dict) or "id" not in data:
            return None

        latest_snapshot = vehicle.snapshots.exclude(soc_kwh__isnull=True).first()
        latest_capacity = vehicle.snapshots.exclude(total_battery_capacity_kwh__isnull=True).first()
        trip, created = Trip.objects.get_or_create(
            vehicle=vehicle,
            source_trip_id=str(data["id"]),
            defaults={
                "started_at": recorded_at,
                "ended_at": recorded_at,
                "distance_miles": self._kilometers_to_miles(data.get("distance", 0)),
                "start_soc_kwh": latest_snapshot.soc_kwh if latest_snapshot else None,
                "battery_capacity_kwh": latest_capacity.total_battery_capacity_kwh if latest_capacity else None,
            },
        )
        if not created:
            trip.ended_at = recorded_at
            trip.distance_miles = self._kilometers_to_miles(data.get("distance", 0))
            if trip.start_soc_kwh is None and latest_snapshot:
                trip.start_soc_kwh = latest_snapshot.soc_kwh
            if trip.battery_capacity_kwh is None and latest_capacity:
                trip.battery_capacity_kwh = latest_capacity.total_battery_capacity_kwh
            trip.save(update_fields=["ended_at", "distance_miles", "start_soc_kwh", "battery_capacity_kwh"])
        return trip

    def _handle_location(self, vehicle, payload, recorded_at):
        data = self._parse_json_payload(payload)
        if not isinstance(data, dict) or "latitude" not in data or "longitude" not in data:
            return None

        trip = self._get_active_trip(vehicle, recorded_at)
        if trip is None:
            trip = Trip.objects.create(vehicle=vehicle, started_at=recorded_at, ended_at=recorded_at)
        elif trip.ended_at < recorded_at:
            trip.ended_at = recorded_at
            trip.save(update_fields=["ended_at"])

        TripPoint.objects.create(
            trip=trip,
            recorded_at=recorded_at,
            sequence=trip.points.count() + 1,
            latitude=Decimal(str(data["latitude"])),
            longitude=Decimal(str(data["longitude"])),
            altitude_m=Decimal(str(data["altitude"])) if data.get("altitude") is not None else None,
        )
        return trip

    def _handle_soc(self, vehicle, payload, recorded_at):
        soc_kwh = Decimal(str(payload))
        snapshot = VehicleSnapshot.objects.create(vehicle=vehicle, recorded_at=recorded_at, soc_kwh=soc_kwh)
        trip = self._get_active_trip(vehicle, recorded_at)
        if trip:
            if trip.start_soc_kwh is None:
                trip.start_soc_kwh = soc_kwh
            trip.end_soc_kwh = soc_kwh
            trip.ended_at = recorded_at
            trip.save(update_fields=["start_soc_kwh", "end_soc_kwh", "ended_at"])
        return snapshot

    def _handle_capacity(self, vehicle, payload, recorded_at):
        capacity_kwh = Decimal(str(payload))
        return VehicleSnapshot.objects.create(
            vehicle=vehicle,
            recorded_at=recorded_at,
            total_battery_capacity_kwh=capacity_kwh,
        )

    def _handle_mileage(self, vehicle, payload, recorded_at):
        odometer_miles = self._kilometers_to_miles(payload)
        return VehicleSnapshot.objects.create(
            vehicle=vehicle,
            recorded_at=recorded_at,
            odometer_miles=odometer_miles,
        )

    def _get_active_trip(self, vehicle, recorded_at):
        return vehicle.trips.filter(ended_at__gte=recorded_at - timedelta(hours=12)).order_by("-ended_at", "-started_at").first()

    @staticmethod
    def _parse_json_payload(payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            return json.loads(payload)
        return payload

    @staticmethod
    def _kilometers_to_miles(kilometers):
        return round(Decimal(str(kilometers)) * Decimal(str(KM_TO_MI)), 2)
