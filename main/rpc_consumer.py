"""
    ref: https://www.jsonrpc.org/specification


    RPCWebSocketConsumer
        - base class for supporting RPC communication
        - supports event subscription
            - use `broadcast_rpc_event(event_name, data=None)` below for publishing events
        - to add a function declare the function name "rpc_{function_name}"
        - rpc functions accept atleast 1 parameter where the first parameter is a RPCRequest object; and
          suceeding parameters used for any purpose
"""

import logging
import json
import inspect
from hashlib import sha256
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger("main")

class RPCError(Exception):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    def __init__(self, *args, code=0, data=None, error_data=None, request=None):
        self.code = code
        self.error_data = error_data
        self.request = request
        return super().__init__(*args)

    def __str__(self):
        return f"{self.__class__.__name__}: {self.message()}"

    def message(self):
        if len(self.args) == 1:
            return self.args[0]

        if self.code == self.PARSE_ERROR:
            return "Parse Error"
        elif self.code == self.INVALID_REQUEST:
            return "Invalid Request"
        elif self.code == self.METHOD_NOT_FOUND:
            return "Method not found"
        elif self.code == self.INVALID_PARAMS:
            return "Invalid Params"
        elif self.code == self.INTERNAL_ERROR:
            return "Internal Error"

        return self.args

    def serialize(self, encode=False):
        data = { "code": self.code, "message": self.message() }
        if self.error_data:
            data["data"] = self.error_data

        if encode:
            data = json.dumps(data)

        return data

    @property
    def response(self):
        return RPCResponse(self.request, error=self)


class RPCRequest(object):

    @classmethod
    def parse_text_data(cls, text_data):
        """
        Returns
            List(RPCRequest | RPCError)
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            raise RPCError(code=RPCError.PARSE_ERROR)

        if not isinstance(data, list):
            data = [data]

        parsed_data=[]
        for _request_data in data:
            if not isinstance(_request_data, dict):
                parsed_data.append(RPCError(code=RPCError.INVALID_REQUEST))
            else:
                parsed_data.append(cls(**_request_data))
        return parsed_data

    def __init__(self, id=None, jsonrpc=None, method="", params=[], **kwargs):
        self.rpc_req_id = id
        self.json_rpc_version = jsonrpc
        self.method_name = method
        self.params = params
        if not isinstance(self.params, list):
            self.params = []

    def __str__(self):
        str_params = [str(p) for p in self.params]
        return f"{self.__class__.__name__}: {self.method_name}({','.join(str_params)})"

    def construct_response(self, result_data, encode=True):
        data= dict(
            json_rpc=self.json_rpc_version,
            id=self.rpc_req_id,
            result=result_data,
        )
        if encode:
            data = json.dumps(data)

        return data


class RPCResponse(object):
    def __init__(self, request, result=None, error=None):
        self.request = request
        self.error = error
        self.result = result

    def serialize(self, encode=True):
        data = dict(result=self.result)
        if isinstance(self.request, RPCRequest):
            data["id"] = self.request.rpc_req_id
            data["jsonrpc"] = self.request.json_rpc_version

        if isinstance(self.error, RPCError):
            data["error"] = self.error.serialize(encode=False)

        if encode:
            data = json.dumps(data)

        return data


class RPCWebSocketConsumer(AsyncJsonWebsocketConsumer):
    @property
    def events(self):
        obj = getattr(self, "_events", None)
        if not isinstance(obj, RPCEventSubscriptionManager):
           self._events = RPCEventSubscriptionManager()
        return self._events

    async def send_update(self, data):
        del data["type"]
        data = data["data"]
        await self.send(json.dumps(data))

    async def send_rpc_response(self, response):
        if not response.request.rpc_req_id:
            return

        return await self.send(text_data=response.serialize(encode=True))

    async def send_batch_rpc_responses(self, responses):
        serialized_responses = []
        for response in responses:
            if not response.request.rpc_req_id:
                continue

            serialized_responses.append(response.serialize(encode=False))
        return await self.send(text_data=json.dumps(serialized_responses))

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        try:
            requests = RPCRequest.parse_text_data(text_data)
        except RPCError as rpc_error:
            logger.info(f"RPC ERROR | {rpc_error.code}")
            return self.send_rpc_response(rpc_error.response)

        responses = []
        for request in requests:
            if isinstance(request, RPCError):
                responses.append(request.response)
                continue

            try:
                response = await self.handle_rpc_request(request)
                logger.info(f"RPC | {request} | {response.result}")
                responses.append(response)
            except RPCError as rpc_error:
                rpc_error.request = request
                logger.exception(rpc_error)
                logger.info(f"RPC ERROR | {rpc_error.code} | {request}")
                responses.append(rpc_error.response)
            except Exception as error:
                rpc_error = RPCError(code=RPCError.INTERNAL_ERROR, request=request)
                logger.exception(error)
                logger.info(f"RPC ERROR | {rpc_error.code} | {request}")
                responses.append(rpc_error.response)

        if len(responses) == 1:
            return await self.send_rpc_response(responses[0])
        else:
            return await self.send_batch_rpc_responses(responses)

    async def handle_rpc_request(self, request):
        func = getattr(self, f"rpc_{request.method_name}", None)
        if not callable(func):
            raise RPCError(code=RPCError.METHOD_NOT_FOUND)

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(request, *request.params)
            else:
                result = func(request, *request.params)
            logger.info(f"RPC FUNC CALL | {func} | {result}")
            return RPCResponse(request, result=result)
        except TypeError as exception:
            logger.exception(exception)
            raise RPCError(code=RPCError.INVALID_PARAMS)
    
    async def rpc_ping(self, request, *args):
        return "PONG"

    async def rpc_subscribe(self, request, event_name, params):
        key_hash = await sync_to_async(self.events.subscribe_event)(event_name, params)
        await self.channel_layer.group_add(f"rpc.{event_name}", self.channel_name)
        return dict(event=event_name, key_hash=key_hash)

    async def rpc_unsubscribe(self, request, event_name, key_hash_or_params=None):
        await sync_to_async(self.events.unsubscribe_event)(event_name, key_hash_or_params=key_hash_or_params)
        await self.channel_layer.group_discard(f"rpc.{event_name}", self.channel_name)

    async def rpc_get_subscriptions(self, request):
        return self.events.subscribed_events

    async def rpc_subscribed_events(self, request):
        return self.events.subscribed_events

    async def rpc_clear_subscribed_events(self, request):
        self.events.subscribed_events = {}

    async def publish_rpc_event(self, data):
        await self.send_rpc_event(data["event"], data["data"])

    async def send_rpc_event(self, event, data):
        if not self.events.is_subscribed_to_event(event, data=data):
            return
        data = dict(jsonrpc="2.0", event=event, data=data)
        await self.send(json.dumps(data))


class RPCEventSubscriptionManager(object):
    def __init__(self):
        self.subscribed_events = {}

    def subscribe_event(self, event, params=None):
        assert isinstance(event, str)
        if not isinstance(self.subscribed_events, dict):
            self.subscribed_events = {}
        
        key = ""
        if params:
            key = json.dumps(params)

        key_hash = sha256(key.encode()).hexdigest()
        if not isinstance(self.subscribed_events, dict):
            self.subscribed_events = {}

        if not isinstance(self.subscribed_events.get(event), dict):
            self.subscribed_events[event] = {}

        self.subscribed_events[event][key_hash] = params
        return key_hash

    def unsubscribe_event(self, event, key_hash_or_params=None):
        assert isinstance(event, str)
        if not isinstance(self.subscribed_events, dict):
            return

        if not key_hash_or_params:
            self.subscribed_events.pop(event, None)
        else:
            if not isinstance(self.subscribed_events.get(event), dict):
                return

            if isinstance(key_hash_or_params, (str, int)):
                self.subscribed_events[event].pop(key_hash_or_params, None)
            if isinstance(key_hash_or_params, dict):
                event_params_map = self.subscribed_events[event]
                _new_event_params_map = {}
                for key_hash, event_params in event_params_map.items():
                    if not self.compare_params(event_params, key_hash_or_params):
                        _new_event_params_map[key_hash] = event_params

                self.subscribed_events[event] = _new_event_params_map

            if not self.subscribed_events[event]:
                self.subscribed_events.pop(event, None)

    def is_subscribed_to_event(self, event, data=None):
        if not isinstance(self.subscribed_events, dict):
            return

        if not self.subscribed_events.get(event):
            return False

        event_params_map = self.subscribed_events[event]
        for key_hash, params in event_params_map.items():
            if self.compare_params(params, data):
                return True

        return False

    def compare_params(self, params, data):
        if not params:
            return True

        if not isinstance(params, dict) and not isinstance(params, dict):
            return True

        for key, value in params.items():
            if value != data.get(key):
                return False

        return True


def broadcast_rpc_event(event_name, data=None):
    room_name = f"rpc.{event_name}"

    channel_layer = get_channel_layer()
    try:
        return async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "publish_rpc_event", "event": event_name, "data": data }
        )
    except RuntimeError:
        return channel_layer.group_send(
            room_name, 
            { "type": "publish_rpc_event", "event": event_name, "data": data }
        )
