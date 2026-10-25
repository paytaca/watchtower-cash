import json
from unittest.mock import patch

import pytest

from main.utils.queries.bchn import BCHN


class FakeSocket:
    def __init__(self, responses):
        self.responses = [json.dumps(response).encode("utf-8") + b"\n" for response in responses]
        self.sent = []
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def makefile(self, mode):
        return self

    def write(self, data):
        self.sent.append(data)

    def flush(self):
        pass

    def readline(self):
        if not self.responses:
            return b""
        return self.responses.pop(0)


def make_node():
    node = BCHN.__new__(BCHN)
    node.fulcrum = {"host": "fulcrum.test", "port": 50001}
    return node


def test_maps_ordered_responses_and_sets_read_timeout():
    socket = FakeSocket([
        {"id": 0, "result": [100, "aa", 0]},
        {"id": 1, "result": None},
        {"id": 2, "result": [200, "bb", 1]},
    ])

    with patch("main.utils.queries.bchn.socket.create_connection", return_value=socket):
        result = make_node().check_addresses_history(["addr-a", "addr-b", "addr-c"])

    assert result == {"addr-a": True, "addr-b": False, "addr-c": True}
    assert socket.timeout == 20
    assert [json.loads(request)["params"][0] for request in socket.sent] == [
        "addr-a",
        "addr-b",
        "addr-c",
    ]


def test_raises_on_fulcrum_error_response():
    socket = FakeSocket([
        {"id": 0, "error": {"code": -5, "message": "No such address"}},
    ])

    with patch("main.utils.queries.bchn.socket.create_connection", return_value=socket):
        with pytest.raises(ValueError, match="get_first_use error"):
            make_node().check_addresses_history(["addr-a"])


def test_raises_on_invalid_request_id(caplog):
    socket = FakeSocket([
        {"id": 99, "result": None},
    ])

    with patch("main.utils.queries.bchn.socket.create_connection", return_value=socket):
        with pytest.raises(ValueError, match="invalid request id"):
            make_node().check_addresses_history(["addr-a"])

    assert "invalid request id: 99" in caplog.text


def test_raises_when_a_requested_address_has_no_result():
    socket = FakeSocket([
        {"id": 0, "result": None},
        {"id": 0, "result": None},
    ])

    with patch("main.utils.queries.bchn.socket.create_connection", return_value=socket):
        with pytest.raises(ValueError, match="no result for addresses: addr-b"):
            make_node().check_addresses_history(["addr-a", "addr-b"])
