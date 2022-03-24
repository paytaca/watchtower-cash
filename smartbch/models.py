from decimal import Decimal
from psqlextra.models import PostgresModel
from django.db import models
from django.db import connection

from django.apps import apps

class Block(PostgresModel):
    block_number = models.DecimalField(max_digits=78, decimal_places=0)

    transactions_count = models.IntegerField(default=0)
    timestamp = models.DateTimeField(null=True, blank=True)

    processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.__class__.__name__}(#{self.block_number})"

    @classmethod
    def get_min_block_number(cls):
        return cls.objects.aggregate(value = models.Min("block_number")).get("value")

    @classmethod
    def get_max_block_number(cls):
        return cls.objects.aggregate(value = models.Max("block_number")).get("value")

    @classmethod
    def get_missing_block_numbers(cls, start_block_number=None, end_block_number=None):
        """
            Gets block numbers not in db in ascending order

        Return
        --------
            (count, iterator): number of block_numbers and an iterator to loop through the list
        """
        if start_block_number is None:
            start_block_number=cls.get_min_block_number()
        
        if end_block_number is None:
            end_block_number = cls.get_max_block_number()

        cursor = connection.cursor()
        cursor.execute(f"""
        WITH block_numbers AS (SELECT block_number FROM {cls._meta.db_table})
        SELECT
            generate_series AS block_number
        FROM
            generate_series({start_block_number}, {end_block_number})
        WHERE
            NOT generate_series IN (SELECT block_number FROM block_numbers)
        """)

        def generator(cursor):
            for row in cursor:
                yield Decimal(row[0])

        return cursor.rowcount, generator(cursor)


class TokenContract(PostgresModel):
    address = models.CharField(max_length=64)

    token_type = models.IntegerField() # erc number e.g. (ERC20, ERC721, ERC777)
    name = models.CharField(max_length=50, null=True, blank=True)
    symbol = models.CharField(max_length=10, null=True, blank=True)

    def __str__(self):
        string = f"{self.__class__.__name__}:{self.address}"
        if self.name:
            string += f" - {self.name}"
        if self.symbol:
            string += f"({self.symbol})"
        return string


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

    @property
    def block_number(self):
        if "block_number" not in self.__dict__:
            self.__dict__["block_number"] = self.block.block_number

        return self.__dict__["block_number"]


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

    @property
    def subscription_model(self):
        attr_name = "subscription_model"
        if attr_name in self.__dict__:
            return self.__dict__[attr_name]

        try:
            model = apps.get_model("main", "Subscription")
            self.__dict__[attr_name] = model
            return model
        except LookupError:
            pass

    @property
    def unit_name(self):
        if self.token_contract:
            return self.token_contract.name
        return "Bitcoin Cash"

    @property
    def unit_symbol(self):
        if self.token_contract:
            return self.token_contract.symbol
        return "BCH"

    def get_subscriptions(self):
        Subscription = self.subscription_model
        if not Subscription:
            return 

        return Subscription.objects.filter(
            address__address__in=[
                self.from_addr,
                self.to_addr,
            ],
        )

    def get_valid_subscriptions(self):
        subscriptions = self.get_subscriptions()
        if not subscriptions:
            return subscriptions

        return subscriptions.filter(
            models.Q(recipient__valid=True) | models.Q(websocket=True)
        )

    def get_unsent_valid_subscriptions(self):
        valid_subs = self.get_valid_subscriptions()
        if not valid_subs:
            return valid_subs

        return valid_subs.filter(
            models.Q(transaction_transfer_logs__sent_at__isnull=True) |
            models.Q(transaction_transfer_logs__isnull=True)
        )

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
