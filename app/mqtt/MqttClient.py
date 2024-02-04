import json
import logging
import socket
import sys
import time
from datetime import datetime

from gmqtt import Client as MQTTClient
from gmqtt import Message as MQTTMessage

from sensors.Alarm import Alarm

logger = logging.getLogger(__name__)

tydom_topic = 'tydom2mqtt/#'
tydom_status_topic = 'tydom2mqtt/state'
refresh_topic = 'homeassistant/requests/tydom/refresh'


class MqttClient:

    def __init__(
            self,
            broker_host="localhost",
            port=1883,
            user="",
            password="",
            mqtt_ssl=False,
            home_zone=1,
            night_zone=2,
            tydom=None,
            tydom_alarm_pin=None):
        self.broker_host = broker_host
        self.port = port
        self.user = user if user is not None else ""
        self.password = password if password is not None else ""
        self.ssl = mqtt_ssl
        self.tydom = tydom
        self.tydom_alarm_pin = tydom_alarm_pin
        self.mqtt_client = None
        self.home_zone = home_zone
        self.night_zone = night_zone
        self.status_topic = tydom_status_topic

    async def connect(self):

        try:
            logger.info(
                'Connecting to mqtt broker (host=%s, port=%s, user=%s, ssl=%s)',
                self.broker_host,
                self.port,
                self.user,
                self.ssl)
            address = socket.gethostname() + str(datetime.fromtimestamp(time.time()))
            will_message = MQTTMessage(tydom_status_topic, 'dead', will_delay_interval=10)
            client = MQTTClient(address, will_message=will_message)
            client.on_connect = self.on_connect
            client.on_message = self.on_message
            client.on_disconnect = self.on_disconnect
            client.set_auth_credentials(self.user, self.password)
            await client.connect(self.broker_host, self.port, self.ssl)
            logger.info('Connected to mqtt broker')
            self.mqtt_client = client
            return self.mqtt_client
        except Exception as e:
            logger.warning("MQTT connection error : %s", e)

    def on_connect(self, client, flags, rc, properties):
        try:
            logger.debug("Subscribing to topics (%s)", tydom_topic)
            client.subscribe('homeassistant/status', qos=0)
            client.subscribe(tydom_topic, qos=0)
        except Exception as e:
            logger.info("Mqtt connection error (%s)", e)

    async def on_message(self, client, topic, payload, qos, properties):
        if 'update' in str(topic):
            value = payload.decode()
            logger.info(
                'update message received (topic=%s, message=%s)',
                topic,
                value)
            await self.tydom.get_data()
        elif 'kill' in str(topic):
            value = payload.decode()
            logger.info(
                'kill message received (topic=%s, message=%s)',
                topic,
                value)
            logger.info('Exiting')
            sys.exit()
        elif topic == "homeassistant/requests/tydom/refresh":
            value = payload.decode()
            logger.info(
                'refresh message received (topic=%s, message=%s)',
                topic,
                value)
            await self.tydom.post_refresh()
        elif topic == "homeassistant/requests/tydom/scenarii":
            value = payload.decode()
            logger.info(
                'scenarii message received (topic=%s, message=%s)',
                topic,
                value)
            await self.tydom.get_scenarii()
        elif topic == "homeassistant/status" and payload.decode() == 'online':
            value = payload.decode()
            logger.info(
                'status message received (topic=%s, message=%s)',
                topic,
                value)
            await self.tydom.get_devices_data()
        elif topic == "/tydom/init":
            value = payload.decode()
            logger.info(
                'init message received (topic=%s, message=%s)',
                topic,
                value)
            await self.tydom.connect()
        
        elif ('set_alarm_state' in str(topic)) and not ('homeassistant' in str(topic)):
            value = payload.decode()
            logger.info(
                'set_alarm_state message received (topic=%s, message=%s)',
                topic,
                value)
            await Alarm.put_alarm_state(tydom_client=self.tydom, asked_state=value, home_zone=self.home_zone, night_zone=self.night_zone)

        elif ('get_alarm_histo' in str(topic)) and not ('homeassistant' in str(topic)):
            value = payload.decode()
            logger.info(
                'get_alarm_histo message received (topic=%s, message=%s)',
                topic,
                value)
            await Alarm.get_alarm_event(tydom_client=self.tydom, asked_state=value)

    @staticmethod
    def on_disconnect(cmd, packet):
        logger.info('Disconnected')
