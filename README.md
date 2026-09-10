# my-mg-dashboard

A small Django monorepo for tracking an MG vehicle lifecycle from the
[`saic-python-mqtt-gateway`](https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway)
MQTT stream.

## What it does

- consumes SAIC MQTT topics for trips, GPS position, state of charge, mileage, and battery capacity
- writes historical vehicle data into Django models that work with PostgreSQL in Docker
- calculates trip efficiency in mi/kWh from journey distance and SOC deltas
- tracks battery degradation over time from total battery capacity samples
- renders a Django + HTMX dashboard with recent trips and a Leaflet map of frequent routes

## Project layout

- `dashboard/services/mqtt.py` ingests the SAIC MQTT gateway topics
- `dashboard/management/commands/consume_saic_mqtt.py` runs the MQTT subscriber
- `dashboard/templates/dashboard/` contains the HTMX dashboard views
- `docker-compose.yml` starts PostgreSQL, Mosquitto, the Django app, the MQTT consumer, and the upstream SAIC gateway container

## Local development

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

To start consuming MQTT updates locally:

```bash
python manage.py consume_saic_mqtt
```

## Docker compose

1. Copy `.env.example` to `.env`
2. Fill in your SAIC username and password
3. Start the stack:

```bash
docker compose up --build
```

The SAIC gateway publishes into Mosquitto and the `ingest` service subscribes to `saic/vehicles/+/...` topics to build historical trip data.

## Running tests

```bash
python manage.py test dashboard
```
