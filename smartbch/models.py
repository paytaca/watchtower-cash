from psqlextra.models import PostgresModel
from django.db import models


class Block(PostgresModel):
    block_number = models.DecimalField(max_digits=78, decimal_places=0)

    transactions_count = models.IntegerField(default=0)
    timestamp = models.DateTimeField(null=True, blank=True)

    processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.__class__.__name__}(#{block_number})"


class TokenContract(PostgresModel):
    address = models.CharField(max_length=64)

    token_type = models.IntegerField() # erc number e.g. (ERC20, ERC721, ERC777)
    name = models.CharField(max_length=50, null=True, blank=True)
    symbol = models.CharField(max_length=10, null=True, blank=True)


class Transaction(PostgresModel):
    txid = models.CharField(max_length=70, db_index=True)
    block = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True
    )

    to_addr = models.CharField(max_length=64)
    from_addr = models.CharField(max_length=64)

    value = models.DecimalField(max_digits=36, decimal_places=18)
    data = models.TextField(null=True, blank=True)
    gas = models.IntegerField()
    gas_price = models.IntegerField()

    is_mined = models.BooleanField(null=True, blank=True)
    status = models.IntegerField(null=True, blank=True) # 0 -> reverted, 1 -> success

    processed_transfers = models.BooleanField(null=True, blank=True)

    def __str__(self):
        return f"{self.__class__.__name__}:{self.txid}"


class TransactionTransfer(PostgresModel):
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="transfers",
    )

    token_contract = models.ForeignKey(
        TokenContract,
        on_delete=models.SET_NULL,
        related_name="transfers",
        null=True,
        blank=True,
    )

    log_index = models.IntegerField(null=True, blank=True)

    to_addr = models.CharField(max_length=64)
    from_addr = models.CharField(max_length=64)

    amount = models.DecimalField(max_digits=36, decimal_places=18, null=True, blank=True)
    token_id = models.IntegerField(null=True, blank=True) # will be applicable to erc721

    def get_subscription_data(self):
        data = {
            "source": "WatchTower",
            "txid": self.transaction.txid,
            "block_number": self.transaction.block.block_number,

            "from": self.from_addr,
            "to": self.to_addr,

            "amount": str(self.amount) if self.amount is not None else None, 
            "token_id": self.token_id,

            "token_contract": {
                "address": "",
                "name": "",
                "symbol": "",
            }
        }

        if self.token_contract:
            self.token_contract.refresh_from_db()

            data["token_contract"] = {
                "address": self.token_contract.address,
                "name": self.token_contract.name,
                "symbol": self.token_contract.symbol,
            }

        return data    


class TransactionTransferReceipientLog(PostgresModel):
    transaction_transfer = models.ForeignKey(
        TransactionTransfer,
        on_delete=models.CASCADE,
        related_name="recipient_logs",
    )
    subscription = models.ForeignKey(
        "main.Subscription",
        on_delete=models.CASCADE,
        related_name="transaction_transfer_logs",
    )

    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (
            ("transaction_transfer", "subscription"),
        )
