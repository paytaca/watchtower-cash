"""Bound, expiring registration challenges and shared request limits."""
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from ecdsa import SECP256k1, VerifyingKey
from ecdsa.errors import MalformedPointError

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.throttling import BaseThrottle

from authentication.token import get_wallet_hash_from_request
from rampp2p.models import RegistrationChallenge, RegistrationRequestBucket
from rampp2p.utils.signature import verify_signature
from rampp2p.viewcodes import ViewCode


CHALLENGE_TTL = timedelta(minutes=5)


def registration_identity(request, account_type):
    wallet_hash = get_wallet_hash_from_request(request)
    public_key = (
        request.headers.get('public-key') or request.headers.get('public_key')
        if account_type == 'peer' else request.data.get('public_key')
    )
    validate_identity(wallet_hash, public_key)
    return wallet_hash, public_key


def validate_identity(wallet_hash, public_key):
    if not isinstance(wallet_hash, str) or not 0 < len(wallet_hash) <= 75:
        raise ValidationError({'wallet_hash': 'A wallet hash of at most 75 characters is required.'})
    if not isinstance(public_key, str) or len(public_key) not in (66, 128, 130):
        raise ValidationError({'public_key': 'A valid secp256k1 public key is required.'})
    try:
        VerifyingKey.from_string(bytes.fromhex(public_key), curve=SECP256k1)
    except (ValueError, MalformedPointError) as err:
        raise ValidationError({'public_key': 'A valid secp256k1 public key is required.'}) from err


def payload_digest(account_type, wallet_hash, public_key, data):
    if account_type not in ('peer', 'arbiter') or not isinstance(data, dict):
        raise ValidationError('A peer or arbiter account_type and registration data object are required.')
    try:
        canonical = json.dumps({
            'account_type': account_type, 'wallet_hash': wallet_hash,
            'public_key': public_key, 'data': dict(data),
        }, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as err:
        raise ValidationError('Registration data must be JSON serializable.') from err
    return hashlib.sha256(canonical.encode()).hexdigest()


def challenge_message(challenge):
    code = ViewCode.PEER_CREATE if challenge.account_type == 'peer' else ViewCode.ARBITER_CREATE
    return f'{code.value}::{challenge.pk}::{challenge.payload_digest}'


def consume_registration_challenge(request, account_type, wallet_hash, public_key):
    """Call inside the same transaction as account creation and reservation use."""
    challenge_id = request.headers.get('registration-challenge') or request.headers.get('registration_challenge')
    signature = request.headers.get('signature')
    try:
        challenge_id = UUID(challenge_id)
    except (ValueError, TypeError, AttributeError) as err:
        raise ValidationError({'registration_challenge': 'A registration challenge is required.'}) from err
    if not isinstance(signature, str) or not 0 < len(signature) <= 160:
        raise ValidationError({'signature': 'A DER signature is required.'})
    try:
        challenge = RegistrationChallenge.objects.select_for_update().get(pk=challenge_id)
    except RegistrationChallenge.DoesNotExist:
        raise PermissionDenied('Invalid registration challenge.')
    now = timezone.now()
    if (challenge.consumed_at is not None or challenge.expires_at <= now
            or challenge.account_type != account_type
            or challenge.payload_digest != payload_digest(account_type, wallet_hash, public_key, request.data)):
        raise PermissionDenied('Registration challenge is expired, consumed, or does not match this request.')
    if not verify_signature(wallet_hash, signature, challenge_message(challenge), public_key=public_key):
        raise PermissionDenied('Invalid registration signature.')
    # The conditional write also prevents replay on databases without row locks.
    if RegistrationChallenge.objects.filter(pk=challenge.pk, consumed_at__isnull=True).update(consumed_at=now) != 1:
        raise PermissionDenied('Registration challenge has already been consumed.')


class RegistrationThrottle(BaseThrottle):
    """Atomic fixed-window limits shared by all application workers."""
    limits = (
        ('ip-minute', 60, 'P2P_REGISTRATION_IP_PER_MINUTE', 10),
        ('ip-day', 86400, 'P2P_REGISTRATION_IP_PER_DAY', 60),
        ('key-minute', 60, 'P2P_REGISTRATION_KEY_PER_MINUTE', 5),
        ('key-day', 86400, 'P2P_REGISTRATION_KEY_PER_DAY', 20),
    )

    def allow_request(self, request, view):
        if not isinstance(request.data, dict):
            raise ValidationError('A registration JSON object is required.')
        now = timezone.now()
        self.retry_after = 0
        # REMOTE_ADDR must be supplied by the trusted reverse proxy. Never trust
        # client-supplied X-Forwarded-For headers here.
        ip = request.META.get('REMOTE_ADDR') or 'unknown'
        key = request.headers.get('public-key') or request.headers.get('public_key') or request.data.get('public_key') or ''
        if not isinstance(key, str):
            key = ''
        for scope, duration, setting, default in self.limits:
            limit = max(1, int(getattr(settings, setting, default)))
            identity = ip if scope.startswith('ip-') else key.lower()
            window = int(now.timestamp()) // duration
            bucket_id = hashlib.sha256(f'{scope}:{identity}:{window}'.encode()).hexdigest()
            expires_at = now.fromtimestamp((window + 1) * duration, tz=now.tzinfo)
            RegistrationRequestBucket.objects.get_or_create(pk=bucket_id, defaults={'expires_at': expires_at})
            updated = RegistrationRequestBucket.objects.filter(pk=bucket_id, attempts__lt=limit).update(attempts=F('attempts') + 1)
            if not updated:
                self.retry_after = max(1, (expires_at - now).total_seconds())
                return False
        return True

    def wait(self):
        return self.retry_after
