"""
Regression tests for the JPP "Payment Request" push notification.

`merchant_data` is caller-supplied, so the address inside it proves nothing.
Before the owner gate, `POST /api/jpp/invoices/` was unauthenticated and the
serializer broadcast a payment request to whatever wallet owned the address the
caller named. Anyone who knew a wallet's address could make the app show that
wallet a payment request; it goes out over MQTT under `notif_type: "TR"` and
looks identical to a genuine one.

These tests pin two things: the push is off unless
`JPP_PAYMENT_REQUEST_PUSH_ENABLED` is set, and once it is on, the broadcast only
fires when the caller authenticated as the wallet holding
`merchant_data["address"]`.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.admin.sites import site
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import AuthToken
from jpp.admin import InvoiceAdmin
from jpp.models import Invoice
from jpp.utils.notification import send_invoice_notifications
from main.models import Address, Wallet


class RecordingMessages:
    """Minimal stand-in for Django's message storage in the admin action."""

    def __init__(self):
        self.messages = []

    def add(self, level, message, extra_tags=""):
        self.messages.append(message)

VICTIM_HASH = "victim-wallet-hash"
ATTACKER_HASH = "attacker-wallet-hash"
VICTIM_ADDRESS = "bitcoincash:qzvictimaddressxxxxxxxxxxxxxxxxxxag4t2q"
ATTACKER_ADDRESS = "bitcoincash:qzattackeraddressxxxxxxxxxxxxxxxxcc8h5w"
NOBODY_ADDRESS = "bitcoincash:qznobodyownsxxxxxxxxxxxxxxxxx7k9y7r4"

BROADCAST_TARGET = "jpp.utils.notification.broadcast_to_engagementhub"


@pytest.fixture
def push_enabled(settings):
    """Turn the push on so the owner gate below is what decides."""
    settings.JPP_PAYMENT_REQUEST_PUSH_ENABLED = True


def make_wallet(wallet_hash, address):
    wallet = Wallet.objects.create(
        wallet_hash=wallet_hash, wallet_type="bch", version=2,
    )
    Address.objects.create(address=address, address_path="0/0", wallet=wallet)
    return wallet


@pytest.fixture
def victim(db):
    return make_wallet(VICTIM_HASH, VICTIM_ADDRESS)


@pytest.fixture
def attacker(db):
    return make_wallet(ATTACKER_HASH, ATTACKER_ADDRESS)


def auth_headers(wallet):
    """The headers a client that authenticated as `wallet` sends."""
    raw_key = "client-held-auth-token-key"
    AuthToken.objects.create(
        wallet_hash=wallet.wallet_hash,
        key=Fernet(settings.FERNET_KEY).encrypt(raw_key.encode()).decode(),
        key_expires_at=timezone.now() + timedelta(days=1),
    )
    return {
        "HTTP_AUTHORIZATION": f"Token {raw_key}",
        "HTTP_WALLET_HASH": wallet.wallet_hash,
    }


def create_invoice(address, **headers):
    return APIClient().post(
        "/api/jpp/invoices/",
        {
            "memo": "invoice",
            "merchant_data": {"address": address},
            "outputs": [{"amount": 100000000, "address": address}],
        },
        format="json",
        **headers,
    )


@patch(BROADCAST_TARGET)
def test_push_disabled_by_default_so_nobody_is_notified(broadcast, victim):
    """The kill switch is off out of the box, even for the address owner."""
    assert settings.JPP_PAYMENT_REQUEST_PUSH_ENABLED is False

    response = create_invoice(VICTIM_ADDRESS, **auth_headers(victim))

    assert response.status_code == 201, response.data
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_disabled_push_reports_disabled_reason(broadcast, victim):
    invoice = Invoice.objects.create(
        expires=timezone.now(), merchant_data={"address": VICTIM_ADDRESS},
    )

    result = send_invoice_notifications(invoice, None, require_owner=False)

    assert result == {"success": False, "reason": "payment request push is disabled"}
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_anonymous_create_naming_victim_address_notifies_nobody(
    broadcast, victim, push_enabled,
):
    response = create_invoice(VICTIM_ADDRESS)

    assert response.status_code == 201, response.data
    assert Invoice.objects.count() == 1
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_address_no_wallet_owns_notifies_nobody(broadcast, db, push_enabled):
    response = create_invoice(NOBODY_ADDRESS)

    assert response.status_code == 201, response.data
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_wallet_hash_header_alone_notifies_nobody(broadcast, victim, push_enabled):
    """A wallet-hash header is not proof: anyone can send someone else's."""
    response = create_invoice(VICTIM_ADDRESS, HTTP_WALLET_HASH=victim.wallet_hash)

    assert response.status_code == 201, response.data
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_authenticated_non_owner_notifies_nobody(broadcast, victim, attacker, push_enabled):
    response = create_invoice(VICTIM_ADDRESS, **auth_headers(attacker))

    assert response.status_code == 201, response.data
    broadcast.assert_not_called()


@patch(BROADCAST_TARGET)
def test_authenticated_owner_notifies_owner(broadcast, victim, push_enabled):
    response = create_invoice(VICTIM_ADDRESS, **auth_headers(victim))

    assert response.status_code == 201, response.data
    broadcast.assert_called_once()
    payload = broadcast.call_args.args[0]
    assert payload["wallet_hash"] == [VICTIM_HASH]
    assert payload["notif_type"] == "TR"


@patch(BROADCAST_TARGET)
def test_admin_action_broadcasts_to_address_owner(broadcast, victim, push_enabled):
    """The Django admin action has no wallet headers; staff is the authority."""
    invoice = Invoice.objects.create(
        expires=timezone.now(), merchant_data={"address": VICTIM_ADDRESS},
    )
    invoice.outputs.create(amount=100000000, address=VICTIM_ADDRESS)
    request = RequestFactory().get("/admin/jpp/invoice/")
    request._messages = RecordingMessages()

    InvoiceAdmin(Invoice, site).send_push_notification(
        request, Invoice.objects.filter(pk=invoice.pk),
    )

    broadcast.assert_called_once()
    assert broadcast.call_args.args[0]["wallet_hash"] == [VICTIM_HASH]


@patch(BROADCAST_TARGET)
def test_missing_merchant_data_address_does_not_broadcast(broadcast, db, push_enabled):
    invoice = Invoice.objects.create(
        expires=timezone.now(), merchant_data={"no_address": True},
    )

    result = send_invoice_notifications(invoice, None, require_owner=False)

    assert result["success"] is False
    broadcast.assert_not_called()
