"""
Unit tests for the P2P status creator payload.

The REST (`StatusSerializer`) and WebSocket (`StatusReadSerializer`) paths must
emit the same creator shape; a live update and a later history fetch of the
same record have to agree. `is_arbiter` is load-bearing because `Peer` and
`Arbiter` have independent primary keys.
"""
from types import SimpleNamespace

from rampp2p import models
from rampp2p.serializers.serializer_status import (
    StatusReadSerializer,
    StatusSerializer,
    serialize_creator,
)


def _status(creator, created_by=None):
    return SimpleNamespace(get_creator=lambda: creator, created_by=created_by)


def _peer(**overrides):
    peer = models.Peer(id=1, name="Peer", chat_identity_id=10)
    for key, value in overrides.items():
        setattr(peer, key, value)
    return peer


def _arbiter(**overrides):
    arbiter = models.Arbiter(id=1, name="Arbiter", chat_identity_id=20)
    for key, value in overrides.items():
        setattr(arbiter, key, value)
    return arbiter


class TestSerializeCreator:
    def test_peer_is_not_arbiter(self):
        assert serialize_creator(_status(_peer())) == {
            "id": 1,
            "name": "Peer",
            "chat_identity_id": 10,
            "is_arbiter": False,
        }

    def test_arbiter_is_flagged(self):
        assert serialize_creator(_status(_arbiter())) == {
            "id": 1,
            "name": "Arbiter",
            "chat_identity_id": 20,
            "is_arbiter": True,
        }

    def test_same_id_disambiguated_by_is_arbiter(self):
        peer = serialize_creator(_status(_peer(id=7)))
        arbiter = serialize_creator(_status(_arbiter(id=7)))
        assert peer["id"] == arbiter["id"] == 7
        assert peer["is_arbiter"] is False
        assert arbiter["is_arbiter"] is True

    def test_system_automated(self):
        assert serialize_creator(_status(None, "SYSTEM_AUTOMATED")) == {
            "id": None,
            "name": None,
            "chat_identity_id": None,
            "is_system": True,
        }

    def test_unresolvable_hash(self):
        assert serialize_creator(_status(None, "some-wallet-hash")) is None


class TestSerializerParity:
    def test_rest_and_websocket_agree_for_peer(self):
        status = _status(_peer())
        rest = StatusSerializer().get_creator(status)
        ws = StatusReadSerializer().get_creator(status)
        assert rest == ws
        assert ws["is_arbiter"] is False

    def test_rest_and_websocket_agree_for_arbiter(self):
        status = _status(_arbiter())
        rest = StatusSerializer().get_creator(status)
        ws = StatusReadSerializer().get_creator(status)
        assert rest == ws
        assert ws["is_arbiter"] is True

    def test_rest_and_websocket_agree_for_system_event(self):
        status = _status(None, "SYSTEM_AUTOMATED")
        assert StatusSerializer().get_creator(status) == StatusReadSerializer().get_creator(status)
