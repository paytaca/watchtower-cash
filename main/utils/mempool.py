from django.utils import timezone
from main.models import (
    Transaction,
    Subscription,
    Address
)
from main.tasks import (
    save_record,
    client_acknowledgement,
    parse_tx_wallet_histories,
    process_cashtoken_tx,
)

import json
import logging

LOGGER = logging.getLogger(__name__)


def process_tx(tx_hash, bchn_client, mqtt_client):
    LOGGER.info('Processing mempool tx: ' + tx_hash)

    tx = bchn_client._get_raw_transaction(tx_hash)
    inputs = tx['vin']
    outputs = tx['vout']

    if 'coinbase' in inputs[0].keys():
        return

    has_subscribed_input = False
    has_updated_output = False
    inputs_data = []

    for _input in inputs:
        txid = _input['txid']
        value = int(_input['value'] * (10 ** 8))
        index = _input['vout']

        tx_check = Transaction.objects.filter(txid=txid, index=index)
        if tx_check.exists():
            ancestor_tx = bchn_client._get_raw_transaction(txid)
            ancestor_spubkey = ancestor_tx['vout'][index]['scriptPubKey']

            if 'addresses' in ancestor_spubkey.keys():
                address = ancestor_spubkey['addresses'][0]
                spent_transactions = Transaction.objects.filter(txid=txid, index=index)
                spent_transactions.update(spent=True, spending_txid=tx_hash)
                has_existing_wallet = spent_transactions.filter(wallet__isnull=False).exists()
                has_subscribed_input = has_subscribed_input or has_existing_wallet

                subscription = Subscription.objects.filter(
                    address__address=address
                )
                if subscription.exists():
                    inputs_data.append({
                        "token": "bch",
                        "address": address,
                        "value": value,
                        "outpoint_txid": txid,
                        "outpoint_index": index,
                    })

    for output in outputs:
        scriptPubKey = output['scriptPubKey']

        if 'addresses' in scriptPubKey.keys():
            bchaddress = scriptPubKey['addresses'][0]

            address_check = Address.objects.filter(address=bchaddress)
            if address_check.exists():
                value = int(output['value'] * (10 ** 8))
                source = bchn_client.source
                index = output['n']

                token_id = 'bch'
                amount = ''
                decimals = None
                created = False
                obj_id = None

                if 'tokenData' in output.keys():
                    saved_token_data = process_cashtoken_tx(
                        output['tokenData'],
                        output['scriptPubKey']['addresses'][0],
                        tx_hash,
                        index=index,
                        value=value
                    )
                    token_id = saved_token_data['token_id']
                    decimals = saved_token_data['decimals']
                    amount = str(saved_token_data['amount'])
                    created = saved_token_data['created']
                else:
                    args = (
                        token_id,
                        bchaddress,
                        tx_hash,
                        source
                    )
                    now = timezone.now().timestamp()
                    obj_id, created = save_record(
                        *args,
                        value=value,
                        blockheightid=None,
                        index=index,
                        inputs=inputs_data,
                        tx_timestamp=now
                    )
                    has_updated_output = has_updated_output or created

                    if obj_id:
                        txn_obj = Transaction.objects.get(id=obj_id)
                        decimals = txn_obj.get_token_decimals()
                    
                if obj_id and created:
                    # Publish MQTT message
                    data = {
                        'txid': tx_hash,
                        'recipient': bchaddress,
                        'token': token_id,
                        'decimals': decimals,
                        'amount': amount,
                        'value': value
                    }

                    if mqtt_client:
                        LOGGER.info('Sending MQTT message: ' + str(data))
                        msg = mqtt_client.publish(f"transactions/{bchaddress}", json.dumps(data), qos=1)
                        LOGGER.info('MQTT message is published: ' + str(msg.is_published()))

                    client_acknowledgement.delay(obj_id)

                    LOGGER.info(data)

    if has_subscribed_input and not has_updated_output:
        LOGGER.info(f"manually parsing wallet history of tx({tx_hash})")
        parse_tx_wallet_histories.delay(tx_hash)
