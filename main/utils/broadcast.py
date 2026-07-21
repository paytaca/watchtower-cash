import json
import logging
from hashlib import md5

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from Crypto.Hash import SHA256  # pycryptodome
from main.mqtt import publish_message
from main.utils.queries.node import Node
from django.apps import apps
from django.conf import settings
from django.utils import timezone

from main.models import Address, Wallet, TransactionBroadcast


NODE = Node()
LOGGER = logging.getLogger(__name__)

BROADCAST_LOCK_KEY_PREFIX = 'broadcast:lock'
BROADCAST_LOCK_TIMEOUT = 30  # seconds


def _get_input_outpoints(tx_hex):
    """Extract input outpoints (txid, vout) from raw transaction hex."""
    tx = NODE.BCH._decode_raw_transaction(tx_hex)
    outpoints = []
    for vin in tx.get('vin', []):
        if 'txid' in vin and 'vout' in vin:
            outpoints.append((vin['txid'], vin['vout']))
    return outpoints


def _acquire_broadcast_locks(outpoints):
    """
    Acquire Redis locks for all input outpoints to prevent concurrent double-spends.
    Returns list of lock keys if all acquired, None if any failed.
    """
    cache = settings.REDISKV
    lock_keys = []
    # Sort outpoints to acquire locks in deterministic order (prevents deadlock)
    sorted_outpoints = sorted(outpoints)
    for txid, vout in sorted_outpoints:
        lock_key = f'{BROADCAST_LOCK_KEY_PREFIX}:{txid}:{vout}'
        acquired = cache.set(lock_key, '1', nx=True, ex=BROADCAST_LOCK_TIMEOUT)
        if acquired:
            lock_keys.append(lock_key)
        else:
            # Failed to acquire lock — another broadcast is using this input
            _release_broadcast_locks(lock_keys)
            return None
    return lock_keys


def _release_broadcast_locks(lock_keys):
    """Release Redis locks for input outpoints."""
    if not lock_keys:
        return
    cache = settings.REDISKV
    for lock_key in lock_keys:
        try:
            cache.delete(lock_key)
        except Exception:
            pass


def broadcast_transaction_sync(transaction_hex, price_log=None, output_fiat_amounts=None):
    """
    Synchronously broadcast a transaction to the BCH node.

    This acquires Redis locks on the transaction's input outpoints to prevent
    concurrent double-spend attempts, then calls test_mempool_accept and
    sendrawtransaction directly. The caller receives the actual result.

    Returns:
        dict: {
            'success': bool,
            'txid': str or None,
            'error': str or None,
            'broadcast_id': int or None,
        }
    """
    result = {'success': False, 'txid': None, 'error': None, 'broadcast_id': None}

    if not NODE.BCH.get_latest_block():
        result['error'] = 'node unavailable'
        return result

    # Extract input outpoints for locking
    try:
        outpoints = _get_input_outpoints(transaction_hex)
    except Exception as exc:
        LOGGER.exception(f'Failed to parse transaction hex: {exc}')
        result['error'] = f'failed to parse transaction: {exc}'
        return result

    if not outpoints:
        result['error'] = 'transaction has no spendable inputs'
        return result

    # Acquire locks on all input outpoints to prevent concurrent double-spends
    lock_keys = _acquire_broadcast_locks(outpoints)
    if lock_keys is None:
        result['error'] = 'transaction inputs are being broadcast by another request'
        return result

    try:
        # Check if transaction would be accepted to mempool
        test_accept = NODE.BCH.test_mempool_accept(transaction_hex)
        txid = test_accept['txid']
        result['txid'] = txid

        if not test_accept['allowed']:
            result['error'] = test_accept.get('reject-reason', 'transaction rejected by mempool')
            return result

        # Create TransactionBroadcast record
        txn_broadcast = TransactionBroadcast(
            txid=txid,
            tx_hex=transaction_hex,
            price_log=price_log,
            output_fiat_amounts=output_fiat_amounts
        )
        txn_broadcast.save()
        result['broadcast_id'] = txn_broadcast.id

        # Actually broadcast to the node
        try:
            broadcasted_txid = NODE.BCH.broadcast_transaction(transaction_hex)
            if broadcasted_txid:
                TransactionBroadcast.objects.filter(id=txn_broadcast.id).update(
                    date_succeeded=timezone.now()
                )
                result['success'] = True
                result['txid'] = broadcasted_txid
                LOGGER.info(f'Synchronous broadcast succeeded for txid {broadcasted_txid}')
            else:
                result['error'] = 'broadcast returned empty txid'
                LOGGER.warning(f'Broadcast returned empty txid for {txid}')
        except Exception as exc:
            error = str(exc)
            if 'already have transaction' in error:
                # Transaction is already in mempool — treat as success
                TransactionBroadcast.objects.filter(id=txn_broadcast.id).update(
                    date_succeeded=timezone.now()
                )
                result['success'] = True
                result['txid'] = txid
                LOGGER.info(f'Transaction {txid} already in mempool')
            else:
                # Real broadcast failure — record error and return failure
                TransactionBroadcast.objects.filter(id=txn_broadcast.id).update(error=error)
                result['error'] = error
                LOGGER.error(f'Broadcast failed for txid {txid}: {error}')
    finally:
        _release_broadcast_locks(lock_keys)

    return result


def send_post_broadcast_notifications(transaction, extra_data:dict=None):
    results = []
    if extra_data:
        try:
            json.dumps(extra_data)
        except:
            extra_data = None

    if not isinstance(extra_data, dict):
        extra_data = {}

    tx = NODE.BCH._decode_raw_transaction(transaction)

    input_0 = tx['vin'][0]
    input_details = NODE.BCH.get_input_details(input_0['txid'], input_0['vout'])
    sender_0 = input_details['address']

    for tx_out in tx['vout']:
        _addrs = tx_out.get('scriptPubKey').get('addresses')
        if _addrs:
            address = _addrs[0]
            device_id = []

            # get device ID from wallet hash of sender_0 address
            try:

                sender_address_obj = Address.objects.get(address=sender_0).wallet.wallet_hash
                if sender_address_obj.wallet and sender_address_obj.wallet.wallet_hash:
                    sender_wallet_hash = sender_address_obj.wallet.wallet_hash
                else:
                    continue

                device_wallet_model = apps.get_model("notifications", "DeviceWallet")
                device_wallet_check = device_wallet_model.objects.filter(wallet_hash=sender_wallet_hash)

                if device_wallet_check.exists():
                    for device in device_wallet_check.all():
                        gcm_device_id = device.gcm_device.device_id
                        apns_device_id = device.apns_device.device_id
                        gcm_device_id_hash = md5(str.encode(gcm_device_id)).hexdigest() if gcm_device_id else None
                        apns_device_id_hash = md5(str.encode(apns_device_id)).hexdigest() if apns_device_id else None
                        
                        if gcm_device_id_hash: device_id.append(gcm_device_id_hash)
                        if apns_device_id_hash: device_id.append(apns_device_id_hash)
                else:
                    device_id = []
            except:
                device_id = []

            # Send mqtt notif
            data = {
                'token': 'bch',
                'txid': tx['txid'],
                'recipient': address,
                'sender_0': sender_0,
                'decimals': 8,
                'value': round(tx_out['value'] * (10 ** 8)),
                'device_id': device_id,
                **extra_data
            }

            addr_obj = Address.objects.filter(address=address).first()
            if addr_obj and addr_obj.wallet and addr_obj.wallet.wallet_hash:
                hash_obj = SHA256.new(addr_obj.wallet.wallet_hash.encode('utf-8'))
                hashed_wallet_hash = hash_obj.hexdigest()
                topic = f"transactions/{hashed_wallet_hash}/{address}"
            else:
                topic = f"transactions/address/{address}"
            
            publish_message(topic, data, qos=1)

            # Send websocket notif
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "bch", 
                {
                    "type": "send_update",
                    "data": data
                }
            )

            results.append(data)
    return results


def broadcast_to_engagementhub(data):
    publish_message('appnotifs', data, qos=0)
