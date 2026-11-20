from channels.generic.websocket import AsyncWebsocketConsumer
import asyncio
from types import SimpleNamespace

from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from authentication.token import TokenAuthentication
from rampp2p.models import Appeal, Arbiter, FeatureControl, Order, OrderMember, Peer, Status
from rampp2p.order_access import order_participant_filter, require_order_participant
from rampp2p.utils.websocket import general_room_name
import json
import logging
logger = logging.getLogger(__name__)

class MarketPriceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.currency = self.scope['url_route']['kwargs']['currency']
        self.room_name = f'p2pxchange_market_price_{self.currency}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'" 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class AdUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.ad_id = self.scope['url_route']['kwargs']['ad_id']
        self.room_name = f'p2pxchange_ad_{self.ad_id}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'" 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class PrivateUpdatesConsumer(AsyncWebsocketConsumer):
    """Authenticate in the first frame, before subscribing to private events."""

    authentication_timeout = 10

    async def connect(self):
        self.credentials = None
        self.room_name = None
        self.user = None
        self.closing = False
        await self.accept()
        self.authentication_task = asyncio.create_task(self.close_if_unauthenticated())

    async def close_if_unauthenticated(self):
        await asyncio.sleep(self.authentication_timeout)
        if self.credentials is None:
            self.closing = True
            await self.close(code=4401)

    async def receive(self, text_data=None, bytes_data=None):
        if self.closing:
            return
        if self.credentials is not None:
            return
        try:
            if text_data is None or len(text_data) > 2048:
                raise ValueError
            data = json.loads(text_data)
            if not isinstance(data, dict) or data.get('type') != 'authenticate':
                raise ValueError
            wallet_hash, token = data.get('wallet_hash'), data.get('token')
            if (not isinstance(wallet_hash, str) or not 0 < len(wallet_hash) <= 100
                    or not isinstance(token, str) or not 0 < len(token) <= 512):
                raise ValueError
        except (TypeError, ValueError):
            self.closing = True
            await self.close(code=4401)
            return

        credentials = (wallet_hash, token)
        user = await self.authorized_user(credentials)
        if user is None or self.closing:
            self.closing = True
            await self.close(code=4403)
            return
        self.authentication_task.cancel()
        self.credentials, self.user = credentials, user
        self.room_name = self.get_room_name()
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        extra = await self.connection_extra()
        await self.send(text_data=json.dumps({
            'success': True, 'type': 'ConnectionMessage',
            'extra': {'message': f"Subscribed to '{self.room_name}'", **extra},
        }))

    @database_sync_to_async
    def authorized_user(self, credentials):
        if FeatureControl.objects.filter(
            name=FeatureControl.Type.P2P_MAINTENANCE, is_enabled=True,
        ).exists():
            return None
        wallet_hash, token = credentials
        request = SimpleNamespace(
            headers={'wallet-hash': wallet_hash, 'Authorization': 'Token ' + token}, META={},
        )
        try:
            user, _ = TokenAuthentication().authenticate(request)
            self.authorize(user)
            return user
        except (APIException, ObjectDoesNotExist, TypeError, ValueError, OverflowError):
            return None

    async def connection_extra(self):
        return {}

    async def disconnect(self, close_code):
        if hasattr(self, 'authentication_task'):
            self.authentication_task.cancel()
        if self.room_name:
            await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def send_message(self, event):
        # Recheck expiry, disabled accounts, maintenance and order assignments
        # before delivering each event on an established connection.
        if self.closing or self.credentials is None:
            return
        if await self.authorized_user(self.credentials) is None:
            self.closing = True
            await self.close(code=4403)
            return
        await self.send(text_data=json.dumps(event.get('message')))


class OrderUpdatesConsumer(PrivateUpdatesConsumer):
    def authorize(self, user):
        order_id = int(self.scope['url_route']['kwargs']['order_id'])
        order = Order.objects.select_related('ad_snapshot__ad').get(pk=order_id)
        require_order_participant(order, user)

    def get_room_name(self):
        order_id = int(self.scope['url_route']['kwargs']['order_id'])
        return f'p2pxchange_order_{order_id}'


class GeneralUpdatesConsumer(PrivateUpdatesConsumer):
    def authorize(self, user):
        if (not isinstance(user, (Peer, Arbiter))
                or user.wallet_hash != self.scope['url_route']['kwargs']['wallet_hash']):
            raise PermissionDenied('Only the account owner may subscribe.')

    def get_room_name(self):
        return general_room_name(self.user.wallet_hash)

    @database_sync_to_async
    def connection_extra(self):
        user = self.user
        # Scope by model and primary key, rather than wallet hash alone.
        members = OrderMember.objects.filter(read_at__isnull=True)
        unread_count, ongoing_count = 0, 0
        if isinstance(user, Peer):
            unread_count = members.filter(peer_id=user.pk).count()
            latest_status = Status.objects.filter(order_id=OuterRef('pk')).order_by('-created_at').values('status')[:1]
            ongoing_count = Order.objects.filter(order_participant_filter(user)).annotate(
                latest_status=Subquery(latest_status),
            ).exclude(latest_status__in=['RLS', 'RFN', 'CNCL']).count()
        else:
            # The arbiter badge counts unread appeals, rather than peer trades.
            unread_count = Appeal.objects.filter(
                order_id__in=members.filter(arbiter_id=user.pk).values('order_id'),
            ).count()
        type(user).objects.filter(pk=user.pk).update(is_online=True, last_online_at=timezone.now())
        return {'unread_count': unread_count, 'ongoing_count': ongoing_count}

    async def disconnect(self, close_code):
        await super().disconnect(close_code)
        if self.user is not None:
            await self.set_offline()

    @database_sync_to_async
    def set_offline(self):
        type(self.user).objects.filter(pk=self.user.pk).update(
            is_online=False, last_online_at=timezone.now(),
        )
