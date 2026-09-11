import logging

from django.conf import settings
from django.core.management.base import BaseCommand
import paho.mqtt.client as mqtt

from dashboard.services.mqtt import SaicMqttIngestor

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume SAIC MQTT gateway messages and persist vehicle history."

    def handle(self, *args, **options):
        ingestor = SaicMqttIngestor(topic_prefix=settings.SAIC_MQTT_TOPIC_PREFIX)
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings.SAIC_MQTT_CLIENT_ID)
        if settings.SAIC_MQTT_USERNAME:
            client.username_pw_set(settings.SAIC_MQTT_USERNAME, settings.SAIC_MQTT_PASSWORD)

        def on_connect(client, userdata, flags, reason_code, properties):
            topic = f"{settings.SAIC_MQTT_TOPIC_PREFIX}/+/vehicles/+/#"
            LOG.info("Connected to MQTT broker; subscribing to %s", topic)
            client.subscribe(topic)

        def on_message(client, userdata, msg):
            try:
                ingestor.ingest(msg.topic, msg.payload.decode("utf-8"))
            except Exception:
                LOG.exception("Failed to process MQTT message for topic %s", msg.topic)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(settings.SAIC_MQTT_HOST, settings.SAIC_MQTT_PORT, keepalive=60)
        client.loop_forever()
