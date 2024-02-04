import json
import logging
from .Sensor import Sensor

logger = logging.getLogger(__name__)
alarm_topic = "tydom2mqtt/alarm_control_panel/#"
alarm_config_topic = "homeassistant/alarm_control_panel/{id}/config"
alarm_state_topic = "tydom2mqtt/alarm_control_panel/{name}/alarm_state"
alarm_command_topic = "tydom2mqtt/alarm_control_panel/{name}/set_alarm_state"
alarm_attributes_topic = "tydom2mqtt/alarm_control_panel/{name}/state"


class Alarm:
    instances = []
    def __init__(self, alarm_pin=None,tydom_attributes_payload=None, mqtt=None):
        self.__class__.instances.append(self)
        self.state_topic = None
        self.device = None
        self.config = None
        self.config_alarm_topic = None
        self.device_id = tydom_attributes_payload['device_id']
        self.device_type = tydom_attributes_payload['device_type']
        self.endpoint_id = tydom_attributes_payload['endpoint_id']
        self.id = tydom_attributes_payload['id']
        self.name = tydom_attributes_payload['name']
        self.attributes = tydom_attributes_payload['attributes']
        self.mqtt = mqtt
        self.alarm_pin = alarm_pin
        self.elements = {}   

    async def setup(self):
        self.device = {
            'manufacturer': 'Delta Dore',
            'model': 'Tyxal',
            'name': self.name,
            'identifiers': self.id
        }
        self.config = {
            'name': None,  # set an MQTT entity's name to None to mark it as the main feature of a device
            'unique_id': self.id,
            'availability_topic': self.mqtt.status_topic,
            'payload_available': 'running',
            'payload_not_available': 'dead',
            'device': self.device,
            'command_topic': alarm_command_topic.format(name=self.name),
            'state_topic': alarm_state_topic.format(name=self.name),
            'code_arm_required': 'false',
        }
        self.config_alarm_topic = alarm_config_topic.format(id=self.id)

        if self.alarm_pin is None:
            self.config['code'] = self.alarm_pin
            self.config['code_arm_required'] = 'true'

        self.config['json_attributes_topic'] = alarm_attributes_topic.format(name=self.name)

        if self.mqtt is not None:
            self.mqtt.mqtt_client.publish(
                self.config_alarm_topic, json.dumps(self.config), qos=0, retain=True)  # Alarm Config

    async def update(self, current_state, tydom_attributes_payload=None):    
        self.current_state = current_state
        if tydom_attributes_payload is not None:
            self.attributes = tydom_attributes_payload['attributes']
        self.state_topic = alarm_state_topic.format(name=self.name, state=self.current_state)
        if self.mqtt is not None:
            self.mqtt.mqtt_client.publish(
                self.state_topic,self.current_state,qos=0,retain=True)  # Alarm State
            self.mqtt.mqtt_client.publish(
                self.config['json_attributes_topic'],self.attributes,qos=0,retain=True)
        logger.info(
            "Alarm created / updated : %s %s %s",
            self.name,
            self.id,
            self.current_state)

    async def update_sensors(self):
        for i, j in self.attributes.items():
            if not i == 'device_type' and not i == 'id' and not i == 'device_id' and not i == 'endpoint_id':
                if i in self.elements:
                    await self.elements[i].update(vars(self))
                else:
                    self.elements[i] = Sensor(
                        elem_name=i,
                        tydom_attributes_payload=vars(self),
                        mqtt=self.mqtt)
                    await self.elements[i].setup()
                    await self.elements[i].update(None)

    @staticmethod
    async def put_alarm_state(tydom_client, home_zone, night_zone, asked_state=None):
        value = None
        zone_id = None
        
        if asked_state == 'ARM_AWAY':
            value = 'ON'
            zone_id = None
        elif asked_state == 'ARM_HOME':  # TODO : Separate both and let user specify with zone is what
            value = "ON"
            zone_id = home_zone
        elif asked_state == 'ARM_NIGHT':  # TODO : Separate both and let user specify with zone is what
            value = "ON"
            zone_id = night_zone
        elif asked_state == 'DISARM':
            value = 'OFF'
            if  Alarm.instances[0].attributes['part1State'] == 'ON':
                zone_id = '1'
            elif  Alarm.instances[0].attributes['part2State'] == 'ON':
                zone_id = '2'
            elif  Alarm.instances[0].attributes['part3State'] == 'ON':
                zone_id = '3'
            elif  Alarm.instances[0].attributes['part4State'] == 'ON':
                zone_id = '4'
            else:
                zone_id = None
        elif asked_state == 'PANIC':
            value = 'PANIC'
            zone_id = None
        elif asked_state == 'ACK':
            value = 'ACK'
            zone_id = None
        if 'part1State' in Alarm.instances[0].attributes:
            zone_cmd = 'partCmd'

        await tydom_client.put_alarm_cdata(device_id=Alarm.instances[0].device_id, alarm_id=Alarm.instances[0].endpoint_id, value=value, zone_cmd=zone_cmd, zone_id=zone_id)

    @staticmethod
    async def get_alarm_event(tydom_client, asked_state=None):
        value = asked_state
        await tydom_client.put_alarm_cdata(device_id=Alarm.instances[0].device_id, alarm_id=Alarm.instances[0].endpoint_id, value=value)
