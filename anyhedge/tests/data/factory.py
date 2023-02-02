import os
import json
import binascii
import struct
import random
import bitcoin
import base64
import hashlib
from cashaddress import convert
from datetime import datetime

from django.conf import settings
from anyhedge.utils.contract import calculate_hedge_sats
from anyhedge.js.runner import AnyhedgeFunctions

SATS_PER_BCH = 10 ** 8

def sha256(message):
    sha256 = hashlib.sha256()
    sha256.update(message.encode("utf-8"))
    return sha256.hexdigest()

def generate_keys():
    priv = bitcoin.random_key()
    pub = bitcoin.compress(bitcoin.privtopub(priv))
    addr = bitcoin.pubtoaddr(pub)
    cashaddr = convert.to_cash_address(addr)

    return (priv, pub, cashaddr)

def num_to_little_endian_hex(value):
    # https://stackoverflow.com/questions/10867193/converting-a-value-into-4-byte-hex-in-python
    unsigned_value = (value + 2**32) % 2**32
    return binascii.hexlify(struct.pack("<I", unsigned_value))

def generate_fake_oracle_message():
    oracle_priv, oracle_pub, _ = generate_keys()
    message_timestamp = int(datetime.now().timestamp())
    message_sequence = int(message_timestamp/60)
    price_sequence = message_sequence - 3
    price = 9_000 + random.randint(0, 2000)

    message_timestamp_hex = num_to_little_endian_hex(message_timestamp)
    message_sequence_hex = num_to_little_endian_hex(message_sequence)
    price_sequence_hex = num_to_little_endian_hex(price_sequence)
    price_hex = num_to_little_endian_hex(price)

    oracle_message_b = message_timestamp_hex + message_sequence_hex + price_sequence_hex + price_hex
    oracle_message = oracle_message_b.decode()

    oracle_signature_b64 = bitcoin.ecdsa_sign(oracle_message_b, oracle_priv)
    oracle_signature_b = base64.b64decode(oracle_signature_b64)
    oracle_signature = binascii.hexlify(oracle_signature_b).decode()

    return {
        "privkey": oracle_priv,
        "pubkey": oracle_pub,
        "message": oracle_message,
        "signature": oracle_signature,
        "price_data": {
            "message_timestamp":  message_timestamp,
            "message_sequence": message_sequence,
            "price_sequence": price_sequence,
            "price": price,
        }
    }

def generate_contract_creation_parameters():
    hedge_priv, hedge_pub, hedge_addr = generate_keys()
    long_priv, long_pub, long_addr = generate_keys()

    random_int = random.randint(1, 200)
    bch_amount = round(0.05 * random_int, 8)

    duration = 60 * random.randint(1, 60 * 24) # 1 hour to 1 day

    low_liquidation_multiplier = (60 + (random.randint(0, 3900)/100)) / 100
    high_liquidation_multiplier = 4

    taker = "hedge" if random.random() > 0.5 else "long"
    maker = "long" if taker == "hedge" else "hedge"

    price = generate_fake_oracle_message()

    hedge_sats = bch_amount * SATS_PER_BCH
    if taker == "long":
        hedge_sats = calculate_hedge_sats(
            long_sats=bch_amount * SATS_PER_BCH,
            low_price_mult=low_liquidation_multiplier,
            price_value=price["price_data"]["price"],
        )

    nominal_units = (hedge_sats * price["price_data"]["price"]) / SATS_PER_BCH

    contract_creation_parameters = dict(
        makerSide=maker,
        takerSide=taker,
        nominalUnits=nominal_units,
        oraclePublicKey=price["pubkey"],
        startingOracleMessage=price["message"],
        startingOracleSignature=price["signature"],
        maturityTimestamp=price["price_data"]["message_timestamp"] + duration,
        highLiquidationPriceMultiplier=high_liquidation_multiplier,
        lowLiquidationPriceMultiplier=low_liquidation_multiplier,
        hedgeMutualRedeemPublicKey=hedge_pub,
        longMutualRedeemPublicKey=long_pub,
        hedgePayoutAddress=hedge_addr,
        longPayoutAddress=long_addr,
        enableMutualRedemption=1,
    )

    data = {
        "creation_parameters": contract_creation_parameters,
        "other": {
            "bch": bch_amount,
            "duration": duration,
            "hedge_keys": {
                "privkey": hedge_priv,
                "pubkey": hedge_pub,
                "address": hedge_addr,
                "wallet_hash": sha256(hedge_priv),
            },
            "long_keys": {
                "privkey": long_priv,
                "pubkey": long_pub,
                "address": long_addr,
                "wallet_hash": sha256(long_priv),
            },
            "price": price,
        },
    }

    return data


def generate_random_contract(save_to_file=None):
    data = generate_contract_creation_parameters()
    data["contract_data"] = AnyhedgeFunctions.compileContract(data["creation_parameters"])

    if save_to_file:
        file_path = os.path.join(settings.BASE_DIR, save_to_file)
        with open(file_path, "w") as outfile:
            outfile.write(json.dumps(data, indent=4))
        print(f"saved to: {file_path}")

    return data

def fetch_saved_test_data():
    file_path = os.path.join(settings.BASE_DIR, "anyhedge/tests/data/anyhedge-test-data.json")
    test_file = open(file_path)
    test_data = json.load(test_file)
    return test_data
