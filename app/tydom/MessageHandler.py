import json
import logging
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler
from io import BytesIO

from sensors.Alarm import Alarm
from sensors.Sensor import Sensor

logger = logging.getLogger(__name__)

# Dicts
deviceAlarmKeywords = [
    'alarmMode',
    'alarmState',
    'alarmSOS',
    'part1State',
    'part2State',
    'part3State',
    'part4State',
    'zone1State',
    'zone2State',
    'zone3State',
    'zone4State',
    'zone5State',
    'zone6State',
    'zone7State',
    'zone8State',
    'gsmLevel',
    'inactiveProduct',
    'zone1State',
    'liveCheckRunning',
    'networkDefect',
    'unitAutoProtect',
    'unitBatteryDefect',
    'unackedEvent',
    'alarmTechnical',
    'systAutoProtect',
    'systBatteryDefect',
    'systSupervisionDefect',
    'systOpenIssue',
    'systTechnicalDefect',
    'videoLinkDefect',
    'outTemperature',
    'kernelUpToDate',
    'irv1State',
    'irv2State',
    'irv3State',
    'irv4State',
    'simDefect',
    'remoteSurveyDefect',
    'systSectorDefect',
]
deviceDoorKeywords = ['autoProtect', 'intrusionDetect', 'battDefect']
deviceWindowKeywords = ['autoProtect', 'intrusionDetect', 'battDefect','motionDetect']

# Device dict for parsing
device_name = dict()
device_endpoint = dict()
device_type = dict()
device_object = {}


class MessageHandler:

    def __init__(self, incoming_bytes, tydom_client, mqtt_client):
        self.incoming_bytes = incoming_bytes
        self.tydom_client = tydom_client
        self.cmd_prefix = tydom_client.cmd_prefix
        self.mqtt_client = mqtt_client

    async def incoming_triage(self):
        bytes_str = self.incoming_bytes
        incoming = None
        first = str(bytes_str[:40])
        try:
            if "Uri-Origin: /refresh/all" in first in first:
                pass
            elif ("PUT /devices/data" in first) or ("/devices/cdata" in first) or ("PUT /areas/data" in first):
                logger.debug(
                    'PUT /devices/data or /areas/data message detected !')
                try:
                    try:
                        incoming = self.parse_put_response(bytes_str)
                    except BaseException:
                        # Tywatt response starts at 7
                        incoming = self.parse_put_response(bytes_str, 7)
                    await self.parse_response(incoming)
                except BaseException:
                    logger.error(
                        'Error when parsing devices/data tydom message (%s)',
                        bytes_str)
                    logger.exception(e)
            elif ("scn" in first):
                try:
                    incoming = self.parse_put_response(bytes_str)
                    await self.parse_response(incoming)
                    logger.debug('Scenarii message processed')
                except BaseException:
                    logger.error(
                        'Error when parsing Scenarii tydom message (%s)', bytes_str)
                    logger.exception(e)
            elif ("POST" in first):
                try:
                    incoming = self.parse_put_response(bytes_str)
                    await self.parse_response(incoming)
                    logger.debug('POST message processed')
                except BaseException:
                    logger.error(
                        'Error when parsing POST tydom message (%s)', bytes_str)
                    logger.exception(e)
            elif ("HTTP/1.1" in first):
                response = self.response_from_bytes(
                    bytes_str[len(self.cmd_prefix):])
                incoming = response.decode("utf-8")
                try:
                    await self.parse_response(incoming)
                except BaseException:
                    logger.error(
                        'Error when parsing HTTP/1.1 tydom message (%s)', bytes_str)
                    logger.exception(e)
            else:
                logger.warning(
                    'Unknown tydom message type received (%s)', bytes_str)

        except Exception as e:
            logger.error(
                'Technical error when parsing tydom message (error=%s), (message=%s)',
                e,
                bytes_str)
            logger.debug('Incoming payload (%s)', incoming)
            logger.exception(e)

    # Basic response parsing. Typically GET responses + instanciate covers and
    # alarm class for updating data
    async def parse_response(self, incoming):
        data = incoming
        msg_type = None
        first = str(data[:40])

        if data != '':
            if "id_catalog" in data:
                msg_type = 'msg_config'
            elif "cmetadata" in data:
                msg_type = 'msg_cmetadata'
            elif "cdata" in data:
                msg_type = 'msg_cdata'
            elif "id" in first:
                msg_type = 'msg_data'
            elif "doctype" in first:
                msg_type = 'msg_html'
            elif "productName" in first:
                msg_type = 'msg_info'

            if msg_type is None:
                logger.warning('Unknown message type received (%s)', data)
            else:
                logger.debug('Message received detected as (%s)', msg_type)
                try:
                    if msg_type == 'msg_config':
                        parsed = json.loads(data)
                        await self.parse_config_data(parsed=parsed)

                    elif msg_type == 'msg_cmetadata':
                        parsed = json.loads(data)
                        await self.parse_cmeta_data(parsed=parsed)

                    elif msg_type == 'msg_data':
                        parsed = json.loads(data)
                        await self.parse_devices_data(parsed=parsed)

                    elif msg_type == 'msg_cdata':
                        parsed = json.loads(data)
                        await self.parse_devices_cdata(parsed=parsed)

                    elif msg_type == 'msg_html':
                        logger.debug("HTML Response ?")
                        logger.debug(data)

                    elif msg_type == 'msg_info':
                        pass
                except Exception as e:
                    logger.error('Error on parsing tydom response (%s)', e)
                    logger.error('Incoming data (%s)', data)
                    logger.exception(e)
            logger.debug('Incoming data parsed with success')

    @staticmethod
    async def parse_config_data(parsed):
        for i in parsed["endpoints"]:
            device_unique_id = str(i["id_endpoint"]) + \
                "_" + str(i["id_device"])

            if  i["last_usage"] == 'window' or i["last_usage"] == 'windowFrench' or i["last_usage"] == 'windowSliding' or i["last_usage"] == 'klineWindowFrench' or i["last_usage"] == 'klineWindowSliding':
                device_name[device_unique_id] = i["name"]
                device_type[device_unique_id] = 'window'
                device_endpoint[device_unique_id] = i["id_endpoint"]

            elif  i["last_usage"] == 'belmDoor' or i["last_usage"] == 'klineDoor':
                device_name[device_unique_id] = i["name"]
                device_type[device_unique_id] = 'door'
                device_endpoint[device_unique_id] = i["id_endpoint"]

            elif i["last_usage"] == 'alarm':
                device_name[device_unique_id] = "Tyxal Alarm"
                device_type[device_unique_id] = 'alarm'
                device_endpoint[device_unique_id] = i["id_endpoint"]

            else:
                device_name[device_unique_id] = i["name"]
                device_type[device_unique_id] = 'unknown'
                device_endpoint[device_unique_id] = i["id_endpoint"]

        logger.debug('Configuration updated')

    async def parse_cmeta_data(self, parsed):
        for i in parsed:
            for endpoint in i["endpoints"]:
                if len(endpoint["cmetadata"]) > 0:
                    for elem in endpoint["cmetadata"]:
                        device_id = i["id"]
                        endpoint_id = endpoint["id"]
                        unique_id = str(endpoint_id) + "_" + str(device_id)

                        if elem["name"] == "energyIndex":
                            device_name[unique_id] = 'Tywatt'
                            device_type[unique_id] = 'conso'
                            for params in elem["parameters"]:
                                if params["name"] == "dest":
                                    for dest in params["enum_values"]:
                                        url = "/devices/" + str(i["id"]) + "/endpoints/" + str(
                                            endpoint["id"]) + "/cdata?name=" + elem["name"] + "&dest=" + dest + "&reset=false"
                                        self.tydom_client.add_poll_device_url(
                                            url)
                                        logger.debug(
                                            "Add poll device : " + url)
                        elif elem["name"] == "energyInstant":
                            device_name[unique_id] = 'Tywatt'
                            device_type[unique_id] = 'conso'
                            for params in elem["parameters"]:
                                if params["name"] == "unit":
                                    for unit in params["enum_values"]:
                                        url = "/devices/" + str(i["id"]) + "/endpoints/" + str(
                                            endpoint["id"]) + "/cdata?name=" + elem["name"] + "&unit=" + unit + "&reset=false"
                                        self.tydom_client.add_poll_device_url(
                                            url)
                                        logger.debug(
                                            "Add poll device : " + url)
                        elif elem["name"] == "energyDistrib":
                            device_name[unique_id] = 'Tywatt'
                            device_type[unique_id] = 'conso'
                            for params in elem["parameters"]:
                                if params["name"] == "src":
                                    for src in params["enum_values"]:
                                        url = "/devices/" + str(i["id"]) + "/endpoints/" + str(
                                            endpoint["id"]) + "/cdata?name=" + elem["name"] + "&period=YEAR&periodOffset=0&src=" + src
                                        self.tydom_client.add_poll_device_url(
                                            url)
                                        logger.debug(
                                            "Add poll device : " + url)

        logger.debug('Metadata configuration updated')

    async def parse_devices_data(self, parsed):
        if (isinstance(parsed, list)):
            for i in parsed:
                if "endpoints" in i:  # case of GET /devices/data
                    for endpoint in i["endpoints"]:
                        await self.parse_endpoint_data(endpoint, i["id"])
                else:  # case of GET /areas/data
                    await self.parse_endpoint_data(i, i["id"])
        elif (isinstance(parsed, dict)):
            await self.parse_endpoint_data(parsed, parsed["id"])
        else:
            logger.error('Unknown data type')
            logger.debug(parsed)

    async def parse_endpoint_data(self, endpoint, device_id):
        if endpoint["error"] == 0 and len(endpoint["data"]) > 0:
            try:
                attr_alarm = {}                
                attr_sensor = {}
                endpoint_attr = {}
                endpoint_id = endpoint["id"]
                unique_id = str(endpoint_id) + "_" + str(device_id)
                name_of_id = self.get_name_from_id(unique_id)
                type_of_id = self.get_type_from_id(unique_id)

                logger.info(
                    'Device update (id=%s, endpoint=%s, name=%s, type=%s)',
                    device_id,
                    endpoint_id,
                    name_of_id,
                    type_of_id)

                for elem in endpoint["data"]:
                    element_name = elem["name"]
                    element_value = elem["value"]
                    element_validity = elem["validity"]
                    print_id = name_of_id if len(
                        name_of_id) != 0 else device_id

                    match type_of_id:
                        case 'door':
                            if element_name in deviceDoorKeywords and element_validity == 'upToDate':
                                attr_sensor['device_id'] = device_id
                                attr_sensor['endpoint_id'] = endpoint_id
                                attr_sensor['id'] = str(device_id) + '_' + str(endpoint_id)
                                attr_sensor['door_name'] = print_id
                                attr_sensor['name'] = print_id
                                attr_sensor['device_type'] = 'door'
                                attr_sensor['changed'] = element_name
                                endpoint_attr[element_name] = element_value
                                attr_sensor['attributes'] = endpoint_attr      
                 
                        case 'window':
                            if element_name in deviceWindowKeywords and element_validity == 'upToDate':
                                attr_sensor['device_id'] = device_id
                                attr_sensor['endpoint_id'] = endpoint_id
                                attr_sensor['id'] = str(device_id) + '_' + str(endpoint_id)
                                attr_sensor['door_name'] = print_id
                                attr_sensor['name'] = print_id
                                attr_sensor['device_type'] = 'window'
                                #attr_sensor['changed'] = element_name
                                endpoint_attr[element_name] = element_value
                                attr_sensor['attributes'] = endpoint_attr      
                    
                        case 'alarm':
                            if element_name in deviceAlarmKeywords and element_validity == 'upToDate':
                                attr_alarm['device_id'] = device_id
                                attr_alarm['endpoint_id'] = endpoint_id
                                attr_alarm['id'] = str(
                                    device_id) + '_' + str(endpoint_id)
                                attr_alarm['alarm_name'] = "Tyxal Alarm"
                                attr_alarm['name'] = "Tyxal Alarm"
                                attr_alarm['device_type'] = 'alarm_control_panel'
                                endpoint_attr[element_name] = element_value
                                attr_alarm['attributes'] = endpoint_attr            
            
                        
            except Exception as e:
                logger.error('msg_data error in parsing !')
                logger.error(e)
                logger.exception(e)

            if 'device_type' in attr_sensor:
                for elem in attr_sensor['attributes'].keys():
                    unique_id = attr_sensor['id'] + '_' + elem
                    if unique_id in device_object:
                        await device_object[unique_id].update(attr_sensor)
                    else:
                        device_object[unique_id] = Sensor(elem,tydom_attributes_payload=attr_sensor,mqtt=self.mqtt_client)
                        await device_object[unique_id].setup()
                        await device_object[unique_id].update(None)
            # Get last known state (for alarm) # NEW METHOD
            elif 'device_type' in attr_alarm and attr_alarm['device_type'] == 'alarm_control_panel':
                state = None
                sos_state = False
                try:

                    if ('alarmState' in attr_alarm['attributes'] and attr_alarm['attributes']['alarmState'] == "ON") or (
                            'alarmState' in attr_alarm['attributes'] and attr_alarm['attributes']['alarmState']) == "QUIET":
                        state = "triggered"

                    elif 'alarmState' in attr_alarm['attributes'] and attr_alarm['attributes']['alarmState'] == "DELAYED":
                        state = "pending"

                    if 'alarmSOS' in attr_alarm['attributes'] and attr_alarm['attributes']['alarmSOS'] == "true":
                        state = "triggered"
                        sos_state = True

                    elif 'alarmMode' in attr_alarm['attributes'] and attr_alarm['attributes']["alarmMode"] == "ON":
                        state = "armed_away"
                    elif 'alarmMode' in attr_alarm['attributes'] and (attr_alarm['attributes']["alarmMode"] == "ZONE" or attr_alarm['attributes']["alarmMode"] == "PART"):
                        state = "armed_home"
                    elif 'alarmMode' in attr_alarm['attributes'] and attr_alarm['attributes']["alarmMode"] == "OFF":
                        state = "disarmed"
                    elif 'alarmMode' in attr_alarm['attributes'] and attr_alarm['attributes']["alarmMode"] == "MAINTENANCE":
                        state = "disarmed"

                    if (sos_state):
                        logger.warning("SOS !")

                    # alarm shall be update Whatever its state because sensor
                    # can be updated without any state
                    unique_id = attr_alarm['id'] + '_alarm'
                    if unique_id in device_object:
                        if not (state is None):
                          await device_object[unique_id].update(state, tydom_attributes_payload=attr_alarm)
                          await device_object[unique_id].update_sensors()
                        else:
                          await device_object[unique_id].update_sensors()
                    else:
                        device_object[unique_id] = Alarm(                           
                            alarm_pin=self.tydom_client.alarm_pin,
                            tydom_attributes_payload=attr_alarm,
                            mqtt=self.mqtt_client)
                        await device_object[unique_id].setup()
                        await device_object[unique_id].update(state)
                        await device_object[unique_id].update_sensors()
                    

                except Exception as e:
                    logger.error("Error in alarm parsing !")
                    logger.error(e)
                    pass
            else:
                pass

    async def parse_devices_cdata(self, parsed):
        for i in parsed:
            for endpoint in i["endpoints"]:
                if endpoint["error"] == 0 and len(endpoint["cdata"]) > 0:
                    try:
                        device_id = i["id"]
                        endpoint_id = endpoint["id"]
                        unique_id = str(endpoint_id) + "_" + str(device_id)
                        name_of_id = self.get_name_from_id(unique_id)
                        type_of_id = self.get_type_from_id(unique_id)
                        logger.info(
                            'Device configured (id=%s, endpoint=%s, name=%s, type=%s)',
                            device_id,
                            endpoint_id,
                            name_of_id,
                            type_of_id)                            

                    except Exception as e:
                        logger.error('Error when parsing msg_cdata (%s)', e)

    # PUT response DIRTY parsing
    def parse_put_response(self, bytes_str, start=6):
        # TODO : Find a cooler way to parse nicely the PUT HTTP response
        resp = bytes_str[len(self.cmd_prefix):].decode("utf-8")
        fields = resp.split("\r\n")
        fields = fields[start:]  # ignore the PUT / HTTP/1.1
        end_parsing = False
        i = 0
        output = str()
        while not end_parsing:
            field = fields[i]
            if len(field) == 0 or field == '0':
                end_parsing = True
            else:
                output += field
                i = i + 2
        parsed = json.loads(output)
        return json.dumps(parsed)

    # FUNCTIONS

    @staticmethod
    def response_from_bytes(data):
        sock = BytesIOSocket(data)
        response = HTTPResponse(sock)
        response.begin()
        return response.read()

    @staticmethod
    def put_response_from_bytes(data):
        request = HTTPRequest(data)
        return request

    def get_type_from_id(self, id):
        device_type_detected = ""
        if id in device_type.keys():
            device_type_detected = device_type[id]
        else:
            logger.warning('Unknown device type (%s)', id)
        return device_type_detected

    # Get pretty name for a device id
    def get_name_from_id(self, id):
        name = ""
        if id in device_name.keys():
            name = device_name[id]
        else:
            logger.warning('Unknown device name (%s)', id)
        return name


class BytesIOSocket:
    def __init__(self, content):
        self.handle = BytesIO(content)

    def makefile(self, mode):
        return self.handle

class HTTPRequest(BaseHTTPRequestHandler):
    def __init__(self, request_text):
        self.raw_requestline = request_text
        self.error_code = self.error_message = None
        self.parse_request()

    def send_error(self, code, message):
        self.error_code = code
        self.error_message = message
