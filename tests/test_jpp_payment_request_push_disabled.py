"""
Regression tests for the JPP "Payment Request" push kill switch.

`merchant_data` is caller-supplied and `POST /api/jpp/invoices/` does not prove
the caller holds the address it names, so the broadcast could be aimed at any
wallet. `JPP_PAYMENT_REQUEST_PUSH_ENABLED` defaults to False and turns the whole
push off regardless of caller.
"""
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import RequestFactory
from django.utils import timezone

from jpp.models import Invoice
from jpp.utils.notification import send_invoice_notifications
from main.models import Address, Wallet

WALLET_HASH = "wallet-hash"
ADDRESS = "bitcoincash:qzvictimaddressxxxxxxxxxxxxxxxxxxag4t2q"

BROADCAST_TARGET = "jpp.utils.notification.broadcast_to_engagementhub"


@pytest.fixture
def owner(db):
    wallet = Wallet.objects.create(wallet_hash=WALLET_HASH, wallet_type="bch", version=2)
    Address.objects.create(address=ADDRESS, address_path="0/0", wallet=wallet)
    return wallet


def make_invoice(**merchant_data):
    invoice = Invoice.objects.create(
        expires=timezone.now(), merchant_data=merchant_data,
    )
    invoice.outputs.create(amount=100000000, address=ADDRESS)
    return invoice


@patch(BROADCAST_TARGET)
def test_push_is_disabled_by_default(broadcast, owner):
    assert settings.JPP_PAYMENT_REQUEST_PUSH_ENABLED is False

    result = send_invoice_notifications(make_invoice(address=ADDRESS), None)

    assert result == {"success": False, "reason": "payment request push is disabled"}
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_push_fires_for_address_owner_once_enabled(broadcast, owner, settings):
    """The switch is the only thing standing between the caller and a push."""
    settings.JPP_PAYMENT_REQUEST_PUSH_ENABLED = True
    request = RequestFactory().get("/api/jpp/invoices/")

    result = send_invoice_notifications(make_invoice(address=ADDRESS), request)

    assert result["success"] is True
    broadcast.assert_called_once()
    assert broadcast.call_args.args[0]["wallet_hash"] == [WALLET_HASH]


@patch(BROADCAST_TARGET)
def test_invoice_create_endpoint_broadcasts_nothing(broadcast, owner):
    """End to end: even naming a real address, the create call notifies nobody."""
    from rest_framework.test import APIClient

    response = APIClient().post(
        "/api/jpp/invoices/",
        {
            "memo": "invoice",
            "merchant_data": {"address": ADDRESS},
            "outputs": [{"amount": 100000000, "address": ADDRESS}],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    broadcast.assert_not_called()

