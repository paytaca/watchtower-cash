import json
import logging
import web3
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from django.conf import settings

from main.models import Address, Subscription


LOGGER = logging.getLogger(__name__)
REDIS_CLIENT = settings.REDISKV

_REDIS_NAME__ADDRESS_CONNECTIONS_CTR = "smartbch:address_consumer-connections_ctr"


class ConsumerAddressCounter:
    @classmethod
    def increment_address(cls, address):
        """
        Return
        --------
            count: int | None
            None implies the address is invalid
        """
        if not web3.Web3.isAddress(address):
            return

        return REDIS_CLIENT.hincrby(_REDIS_NAME__ADDRESS_CONNECTIONS_CTR, address, 1)

    @classmethod
    def decrement_address(cls, address):
        """
        Return
        --------
            count: int | None
            None implies the address is invalid
        """
        if not web3.Web3.isAddress(address):
            return

        count = REDIS_CLIENT.hincrby(_REDIS_NAME__ADDRESS_CONNECTIONS_CTR, address, -1)
        if count <= 0:
            REDIS_CLIENT.hdel(_REDIS_NAME__ADDRESS_CONNECTIONS_CTR, address)

        return count

    @classmethod
    def get_address_count(cls, address):
        """
        Get the number connections listening to the address
        
        Return
        --------
            has_members: bool | None
        """
        if not web3.Web3.isAddress(address):
            return
        try:
            value = REDIS_CLIENT.hget(_REDIS_NAME__ADDRESS_CONNECTIONS_CTR, address)
            value = int(value)
            return value
        except (ValueError, TypeError):
            REDIS_CLIENT.hdel(_REDIS_NAME__ADDRESS_CONNECTIONS_CTR, address)

    @classmethod
    def address_has_members(cls, address):
        """
        Checks if there are connections listening to the address
        
        Return
        --------
            has_members: bool | None
        """
        count = cls.get_address_count(address)
        if count is None:
            return

        return count >= 1


class TransactionTransferUpdatesConsumer(WebsocketConsumer):
    CONTRACT_ADDRESS_LOOKUP_NAME = "contract_address"

    def connect(self):
        self.address = self.scope["url_route"]["kwargs"]["address"]
        self.contract_address = ""
        if CONTRACT_ADDRESS_LOOKUP_NAME in self.scope["url_route"]["kwargs"].keys():
            self.CONTRACT_ADDRESS_LOOKUP_NAME = self.scope["url_route"]["kwargs"][CONTRACT_ADDRESS_LOOKUP_NAME]

        if not web3.Web3.isAddress(self.address):
            LOGGER.info(f"Invalid address for websocket update connections: {self.address}")
            self.close()
            return

        self.room_name = self.address
        if self.contract_address:
            if not web3.Web3.isAddress(self.contract_address):
                LOGGER.info(
                    f"Provided contract address for websocket update connections but invalid: {self.contract_address}"
                )
                self.close()
                return

            self.room_name += f"_{self.contract_address}"

        count = ConsumerAddressCounter.increment_address(self.address)
        LOGGER.info(f"address({self.address}) has {count} websocket connection/s")
        LOGGER.info(f"updating subscriptions for address({self.address}), enabling websocket")
        Subscription.objects.filter(address__address=self.address).update(websocket=True)

        LOGGER.info(f"ADDRESS {self.room_name} CONNECTED!")
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        LOGGER.info(f"ADDRESS {self.room_name} DISCONNECTED!")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )

        # need to maintain a counter for address in the event of
        # multiple clients listening to the same address
        count = ConsumerAddressCounter.decrement_address(self.address)
        LOGGER.info(f"address({self.address}) has {count} websocket connection/s remaining")
        if not ConsumerAddressCounter.address_has_members(self.address):
            LOGGER.info(f"updating subscriptions for address({self.address}), disabling websocket")
            Subscription.objects.filter(address__address=self.address).update(websocket=False)

    def send_update(self, data):
        logging.info(f"FOUND {data}")
        del data["type"]
        data = data["data"]
        self.send(text_data=json.dumps(data))
