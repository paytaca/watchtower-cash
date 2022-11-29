"""
    ref: https://www.jsonrpc.org/specification

    RPCWebSocketConsumer
        - to add a function declare the function name "rpc_{function_name}"
        - rpc functions accept atleast 1 parameter where the first parameter is a RPCRequest object; and
          suceeding parameters used for any purpose
"""

import logging
import json
import inspect
from asgiref.sync import async_to_sync

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
    async def send_update(self, data):
        del data["type"]
        data = data["data"]
        await self.send(json.dumps(data))

    async def send_rpc_response(self, response):
        return await self.send(text_data=response.serialize(encode=True))

    async def send_batch_rpc_responses(self, responses):
        serialized_responses = []
        for response in responses:
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
                rpc_error = RPCError(code=RPCError.INTERNAL_ERROR)
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
        except TypeError:
            raise RPCError(code=RPCError.INVALID_PARAMS)
