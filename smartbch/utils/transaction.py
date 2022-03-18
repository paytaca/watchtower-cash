import decimal
from smartbch.models import Block, Transaction, TokenContract

from .contract import abi
from .web3 import create_web3_client

def save_transaction(txid):
    w3 = create_web3_client()
    transaction = w3.eth.get_transaction(txid)

    block_obj, created = Block.objects.get_or_create(
        block_number=decimal.Decimal(transaction.blockNumber),
    )

    tx, created = Transaction.objects.get_or_create(
        txid=transaction.hash.hex(),
        defaults = {
            "block": block_obj,
            "to_addr": transaction.to,
            "from_addr": transaction['from'],
            "value": w3.fromWei(transaction.value, 'ether'),
            "data": transaction.input,
            "gas": transaction.gas,
            "gas_price": transaction.gasPrice,
            "is_mined": True,
        }
    )

    return tx


def save_transaction_transfers(txid):
    instance = Transaction.objects.filter(txid=txid).first()

    if not instance:
        return

    w3 = create_web3_client()
    receipt = w3.eth.get_transaction_receipt(instance.txid)

    erc20 = w3.eth.contract('', abi=abi.get_token_abi(20))
    erc721 = w3.eth.contract('', abi=abi.get_token_abi(721))

    erc20_transfers = erc20.events.Transfer().processReceipt(receipt)
    erc721_transfers = erc721.events.Transfer().processReceipt(receipt)

    print(f"erc20: {erc20_transfers}")
    print(f"erc721: {erc721_transfers}")


    if len(erc20_transfers):
        for event_log in erc20_transfers:
            token_contract_instance, _ = TokenContract.objects.get_or_create(
                address=event_log.address,
                defaults={
                    "token_type": 20,
                }
            )

            instance.transfers.update_or_create(
                token_contract=token_contract_instance,
                log_index=event_log.logIndex,
                defaults = {
                    "to_addr": event_log.args.to,
                    "from_addr": event_log.args["from"],
                    "amount": decimal.Decimal(event_log.args.value) / 10 ** 18,
                    "token_id": None,
                }
            )

    if len(erc721_transfers):
        for event_log in erc721_transfers:
            token_contract_instance, _ = TokenContract.objects.get_or_create(
                address=event_log.address,
                defaults={
                    "token_type": 721,
                }
            )

            instance.transfers.update_or_create(
                token_contract=token_contract_instance,
                log_index=event_log.logIndex,
                defaults = {
                    "to_addr": event_log.args.to,
                    "from_addr": event_log.args["from"],
                    "amount": None,
                    "token_id": event_log.args.tokenId,
                }
            )

    # This part is for checking whether the transaction has transferred some bch
    if instance.value > 0:
        instance.transfers.update_or_create(
            token_contract=None,
            log_index=None,
            defaults = {
                "to_addr": instance.to_addr,
                "from_addr": instance.from_addr,
                "amount": instance.value,
                "token_id": None,
            }
        )

    instance.processed_transfers = True
    instance.status = receipt.status
    instance.save()

    return instance
