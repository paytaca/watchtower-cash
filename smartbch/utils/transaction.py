import decimal
import warnings
from web3.datastructures import AttributeDict
from smartbch.models import Block, Transaction, TokenContract

from .contract import abi
from .formatters import format_block_number
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

    erc20_transfers = []
    erc721_transfers = []

    with warnings.catch_warnings(record=True) as w:
        erc20_transfers = erc20.events.Transfer().processReceipt(receipt)
        erc721_transfers = erc721.events.Transfer().processReceipt(receipt)

    # print(f"erc20: {erc20_transfers}")
    # print(f"erc721: {erc721_transfers}")

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

def get_transactions_by_address(address, from_block=0, to_block=0, block_partition=0):
    """
        Generator function that yields transactions of a given address within a block range
        Also includes SEP20 & SEP721 Transfer events

    Parameters
    ------------
        address: stirng
            Hex string of wallet address
        from_block: int
            Start block to crawl through the blockchain
        to_block: int
            End block to crawl through the blockchain
        block_partition: int
            Will cause to iterate from start block to end block by N blocks.
            A means to avoid burst request
    Yield
    ------------
        tx_list: AttributeDict({
            "from_block": "0x00",
            "to_block": "0x00",
            "transactions": [
                AttributeDict({
                    "hash": "0x00",
                    "block_hash": "0x00",
                    "block_number": 0,
                    "transaction_index": 0,
                })
            ]
        })
    """
    w3 = create_web3_client()
    if not w3.isAddress(address):
        return

    # We add option to partition by a number of blocks to have the option to avoid burst of requests
    block_markers=[from_block, to_block]
    if block_partition > 0 and block_partition % 1 == 0:
        block_markers = [*range(from_block, to_block, block_partition), to_block]

    block_markers[0] -= 1
    for i in range(len(block_markers)-1):
        tx_map = {}
        start_block = format_block_number(block_markers[i-1]+1)
        end_block = format_block_number(block_markers[i])
        txs = w3.sbch.query_tx_by_addr(
            address,
            start_block,
            end_block,
            "0x0",
        )
        transfer_txs = w3.sbch.query_transfer_events(
            wallet_address=address,
            from_block=start_block,
            to_block=end_block,
        )

        for tx in txs:
            tx_map[tx.hash] = AttributeDict({
                "hash": tx.hash,
                "block_hash": tx.blockHash,
                "block_number": int(tx.blockNumber, 16),
                "transaction_index": int(tx.transactionIndex, 16),
            })

        for log in transfer_txs:
            tx_map[log.transactionHash.hex()] = AttributeDict({
                "hash": log.transactionHash.hex(),
                "block_hash": log.blockHash.hex(),
                "block_number": log.blockNumber,
                "transaction_index": log.transactionIndex,
            })

        yield AttributeDict({
            "from_block": start_block,
            "to_block": end_block,
            "transactions": [*tx_map.values()],
        })


def save_transactions_by_address(address, from_block=0, to_block=0, block_partition=0):
    """Save transactions of a given address
        Includes ERC20 & ERC721 Transfer event
 
    Parameters
    ------------
        address: stirng
            Hex string of wallet address
        from_block: int
            Start block to crawl through the blockchain
        to_block: int
            End block to crawl through the blockchain
        block_partition: int
            Will cause to iterate from start block to end block by N blocks.
            A means to avoid burst request
    Return
    -----------
        saved_transactions: Array[smartbch.models.Transaction]
            List of smartbch.models.Transaction instances saved to db
            Transactions that existed already are not included here
    """
    saved_transactions = []
    iterator = get_transactions_by_address(
        address,
        from_block=from_block,
        to_block=to_block,
        block_partition=block_partition
    )
    for tx_list in iterator:
        unique_txids = set()
        for tx in tx_list.transactions:
            unique_txids.add(tx.hash)

        # save transactions that are not yet in db
        saved_txs_queryset = Transaction.objects.filter(txid__in=unique_txids)
        saved_tx_txids = {x for x in saved_txs_queryset.values_list('txid', flat=True)}
        for txid in (unique_txids - saved_tx_txids):
            tx_obj = save_transaction(txid)
            saved_transactions.append(tx_obj)

        # save transfers for transactions that are not yet parsed
        transfer_saved_queryset = Transaction.objects.filter(txid__in=unique_txids, processed_transfers=True)
        transfer_saved_tx_txids = {x for x in transfer_saved_queryset.values_list('txid', flat=True)}
        for txid in (unique_txids-transfer_saved_tx_txids):
            save_transaction_transfers(txid)

    return saved_transactions
