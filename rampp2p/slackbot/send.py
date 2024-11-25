from slack import WebClient
from slack.errors import SlackApiError
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
from enum import Enum
from rampp2p.utils import satoshi_to_bch, bch_to_fiat

from . import block_kit
from . import block_kit_helpers

import rampp2p.models as models
import logging
logger = logging.getLogger(__name__)

class MessageBase(object):
    @classmethod
    def get_client(cls, token=settings.P2P_EXCHANGE_SLACKBOT_USER_TOKEN):
        return WebClient(token=token)

    @classmethod
    def update_message(cls, channel=settings.P2P_EXCHANGE_SLACK_CHANNEL, ts="", text=None, blocks=[], attachments=[]):
        slack_client = cls.get_client()
        logger.info(f"SLACK UPDATE MESSAGE | {channel} | {ts} | text={text} | blocks={blocks} | attachments={attachments}")
        try:
            response = slack_client.chat_update(
                text = text,
                channel=channel,
                ts=ts,
                blocks=blocks,
                attachments=attachments,
            )

            return dict(
                success=response.data.get("ok"), 
                channel=response.data.get("channel"),
                ts=response.data.get("ts"),
                response_data=response.data,
            )
        except SlackApiError as error:
            return dict(
                success=error.response["ok"], 
                error=error.response["error"]
            )

    @classmethod
    def send_message(cls, channel=settings.P2P_EXCHANGE_SLACK_CHANNEL, text=None, blocks=[], attachments=[], thread_ts=None, reply_broadcast=False):
        slack_client = cls.get_client()

        logger.info(f"SLACK POST MESSAGE | {channel} {('| ' + thread_ts) if thread_ts else ''} | text={text} | blocks={blocks} | attachments={attachments}")
        try:
            response = slack_client.chat_postMessage(
                text = text,
                channel=channel,
                blocks=blocks,
                attachments=attachments,
                thread_ts=thread_ts,
                reply_broadcast=reply_broadcast,
            )

            return dict(
                success=response.data.get("ok"), 
                message=f"Sent to {response.data.get('channel')} at {response.data.get('ts')}",
                channel=response.data.get("channel"),
                ts=response.data.get("ts"),
                response_data=response.data,
            )
        except SlackApiError as error:
            return dict(
                success=error.response["ok"], 
                error=error.response["error"]
            )

    @classmethod
    def delete_message(cls, channel, ts, update_db=True):
        slack_client = cls.get_client()
        logger.info(f"SLACK DELETE MESSAGE | {channel} | {ts}")
        try:
            response = slack_client.chat_delete(channel=channel, ts=ts)
            if response.data.get("ok") and update_db:
                models.SlackMessageLog.objects.filter(
                    channel=response.data.get("channel"),
                    ts=response.data.get("ts"),
                ).update(deleted_at=timezone.now())

            return dict(
                success=response.data.get("ok"), 
                channel=response.data.get("channel"),
                ts=response.data.get("ts"),
                response_data=response.data,
            )
        except SlackApiError as error:
            return dict(
                success=error.response["ok"], 
                error=error.response["error"]
            )
    
    @classmethod
    def get_env_context_block(cls):
        """
            Add additional context if the message is sent from staging/development
            - environment is determined by ENV in settings.py
        """
        env = None
        if settings.ENV in ["dev", "development"]:
            env = "development"
        elif settings.ENV in ["stg", "staging"]:
            env = "staging"

        if env:
            return {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Sent from `{env}`"
                    }
                ],
            }

class OrderSummaryMessage(MessageBase):
    @classmethod
    def send_safe(cls, *args, **kwargs):
        try:
            return cls.send(*args, **kwargs)
        except Exception as exception:
            logger.exception(exception)
            return exception

    @classmethod
    def send(cls, order_id:int, channel:str=None):
        order = models.Order.objects.filter(id=order_id).first()
        if not order:
            return

        blocks = [
            cls.get_message_header_block(order),
            *cls.get_order_details_block(order),
            block_kit.Divider(),
            *cls.get_summary_block(order),
            cls.get_created_at_block(order),
        ]

        text=f"{order.trade_type.lower().capitalize()} Order #{order.id} Summary"
        if order.is_cash_in:
            text = f"Cash In {text}"
        attachments = [
            block_kit.Blocks(*blocks, color=cls.resolve_color_from_status(order)),
        ]
        msg_logs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.ORDER_SUMMARY,
            object_id=order.id,
            deleted_at__isnull=True,
        )

        send_new = True
        results = []
        for msg_log in msg_logs:
            result = cls.update_message(
                channel=msg_log.channel,
                ts=str(msg_log.ts),
                attachments=attachments,
            )

            if (result["success"] or result.get("error") != "message_not_found") and \
                (not channel or msg_log.channel == channel):
                send_new = False

            results.append(result)

        if send_new:
            kwargs = dict(text=text, attachments=attachments)
            if channel: kwargs["channel"] = channel
            result = cls.send_message(**kwargs)
            results.append(result)

        for result in results:
            if not result.get("success"):
                continue

            models.SlackMessageLog.objects.update_or_create(
                topic=models.SlackMessageLog.Topic.ORDER_SUMMARY,
                object_id=order.id,
                channel=result["channel"],
                defaults=dict(
                    ts=result["ts"],
                    deleted_at=None,
                )
            )

        return results
    
    @classmethod
    def resolve_color_from_status(cls, order:models.Order):
        return block_kit_helpers.resolve_color_from_order_status(order.status.status)

    @classmethod
    def get_message_header_block(cls, order:models.Order):
        header_text = f'{order.trade_type.lower().capitalize()} Order #{order.id} Summary'
        if order.is_cash_in:
            header_text = f'Cash In {header_text}'
        plain_text = block_kit.PlainText(header_text)
        header = block_kit.Header(plain_text)
        return header

    @classmethod
    def get_order_details_block(cls, order:models.Order):
        status_label = models.StatusType(order.status.status).label

        blocks = [
            
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Status*\n{status_label}"),
                block_kit.Markdown(f"*Created by*\n{order.owner.name}"),
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Order ID*\n{order.id}"),
                block_kit.Markdown(f"*Tracking ID*\n{order.tracking_id}")
            ])
        ]

        return blocks

    @classmethod
    def get_summary_block(cls, order:models.Order):
        currency = order.currency.symbol
        ad_owner = order.ad_snapshot.owner.name
        ad_price = order.ad_snapshot.price
        bch_amount = satoshi_to_bch(order.trade_amount)
        trade_amount = '{:.10f}'.format(float(str(bch_amount))).rstrip('0').rstrip('.')
        fiat_trade_amount = '{:.2f}'.format(bch_to_fiat(bch_amount, ad_price))

        blocks = [
            block_kit.SectionBlock(
                text=block_kit.Markdown(":page_with_curl: *Trade Summary:*"),
                fields=[
                    block_kit.Markdown(f"*Ad ID*\n{order.ad_snapshot.ad.id}"),
                    block_kit.Markdown(f"*Ad Owner*\n{ad_owner}")
                ]
            ),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Price*\n{ad_price:.2f} {currency}"),
                block_kit.Markdown(f"*Amount*\n{trade_amount} BCH ({fiat_trade_amount} {currency})"),
            ])
        ]
        return blocks

    @classmethod
    def get_created_at_block(self, order:models.Order):
        created_at = order.created_at
        if isinstance(created_at, str):
            created_at = datetime.strptime(order.created_at, "%Y-%m-%dT%H:%M:%S%z")

        return block_kit.ContextBlock(
            block_kit.Markdown(f"Order created {block_kit_helpers.format_timestamp(created_at)}")
        )

class OrderStatusUpdateMessage(MessageBase):
    @classmethod
    def send_safe(cls, *args, **kwargs):
        try:
            return cls.send(*args, **kwargs)
        except Exception as exception:
            logger.exception(exception)
            return exception

    @classmethod
    def send(cls, order_id:int, status=None):
        order = models.Order.objects.filter(id=order_id).first()

        if not order:
            return

        if not status:
            status = order.status

        msg_kwargs = cls.build(order, status=status.status)
        if not msg_kwargs:
            return

        summary_msgs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.ORDER_SUMMARY,
            object_id=order.id,
            deleted_at__isnull=True,
        ).values("channel", "ts").distinct()

        results = []
        for thread_data in summary_msgs:
            channel = thread_data["channel"]
            thread_ts = str(thread_data["ts"])
            result = dict(channel=channel, thread_ts=thread_ts)

            response = cls.send_message(
                channel=channel,
                thread_ts=thread_ts,
                reply_broadcast=True,
                **msg_kwargs,
            )
            result.update(response)

            if response["success"]:
                models.SlackMessageLog.objects.create(
                    topic=models.SlackMessageLog.Topic.ORDER_STATUS_UPDATE,
                    object_id=order.id,
                    metadata=dict(status=status.status),
                    channel=response["channel"],
                    ts=response["ts"],
                    thread_ts=thread_ts,
                    deleted_at=None,
                )

            results.append(result)

        return dict(results=results)

    @classmethod
    def build(cls, order:models.Order, status=None):
        if not status:
            status = order.status

        text = cls.get_text(order, status=status)

        if not text:
            return

        return dict(
            text=text
        )

    @classmethod
    def get_text(cls, order:models.Order, status=None):
        if not status:
            status = order.status
        
        if status == models.StatusType.SUBMITTED:
            return f"Order #{order.id} submitted"
        elif status == models.StatusType.CONFIRMED:
            return f"Order #{order.id} confirmed"
        elif status == models.StatusType.ESCROW_PENDING:
            return f"Order #{order.id} validating escrow"
        elif status == models.StatusType.ESCROWED:
            return f"Order #{order.id} escrowed"
        elif status == models.StatusType.PAID_PENDING:
            return f"Order #{order.id} awaiting payment confirmation"
        elif status == models.StatusType.PAID:
            return f"Order #{order.id} payment confirmed"
        elif status == models.StatusType.APPEALED:
            return f"Order #{order.id} appealed"
        elif status == models.StatusType.RELEASE_PENDING:
            return f"Order #{order.id} validating release"
        elif status == models.StatusType.RELEASED:
            return f"Order #{order.id} released :tada:"
        elif status == models.StatusType.REFUND_PENDING:
            return f"Order #{order.id} validating refund"
        elif status == models.StatusType.REFUNDED:
            return f"Order #{order.id} refunded"
        elif status == models.StatusType.CANCELED:
            return f"Order #{order.id} canceled"
        else:
            return ""

class AppealSummaryMessage(MessageBase):
    @classmethod
    def send_safe(cls, *args, **kwargs):
        try:
            return cls.send(*args, **kwargs)
        except Exception as exception:
            logger.exception(exception)
            return exception

    @classmethod
    def send(cls, appeal_id:int, channel:str=None):
        appeal = models.Appeal.objects.filter(id=appeal_id).first()
        if not appeal:
            return

        # Build the message blocks
        blocks = [
            cls.get_message_header_block(appeal),
            *cls.get_appeal_details_block(appeal),
            cls.get_created_at_block(appeal),
        ]

        text=f"Appeal #{appeal.id} Summary"
        attachments = [
            block_kit.Blocks(*blocks, color=cls.resolve_color_from_status(appeal)),
        ]
        msg_logs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.APPEAL_SUMMARY,
            object_id=appeal.id,
            deleted_at__isnull=True,
        )

        send_new = True
        results = []
        for msg_log in msg_logs:
            result = cls.update_message(
                channel=msg_log.channel,
                ts=str(msg_log.ts),
                attachments=attachments,
            )

            if (result["success"] or result.get("error") != "message_not_found") and \
                (not channel or msg_log.channel == channel):
                send_new = False

            results.append(result)

        if send_new:
            kwargs = dict(text=text, attachments=attachments)
            if channel: kwargs["channel"] = channel
            result = cls.send_message(**kwargs)
            results.append(result)

        for result in results:
            if not result.get("success"):
                continue

            models.SlackMessageLog.objects.update_or_create(
                topic=models.SlackMessageLog.Topic.APPEAL_SUMMARY,
                object_id=appeal.id,
                channel=result["channel"],
                defaults=dict(
                    ts=result["ts"],
                    deleted_at=None,
                )
            )

        return results
    
    @classmethod
    def resolve_color_from_status(cls, appeal:models.Appeal):
        return block_kit_helpers.resolve_color_from_appeal_status(appeal)
    
    @classmethod
    def resolve_status(cls, appeal:models.Appeal):
        status = 'Pending'
        if appeal.resolved_at:
            order_status = appeal.order.status.status
            if order_status == models.StatusType.REFUND_PENDING:
                status = models.StatusType.REFUNDED.label
            elif order_status == models.StatusType.RELEASE_PENDING:
                status = models.StatusType.RELEASED.label
        return status

    @classmethod
    def get_message_header_block(cls, appeal:models.Appeal):
        header_text = f'Appeal #{appeal.id} Summary'
        plain_text = block_kit.PlainText(header_text)
        header = block_kit.Header(plain_text)
        return header

    @classmethod
    def get_appeal_details_block(cls, appeal:models.Appeal):
        status_label = cls.resolve_status(appeal)

        blocks = [
            
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Status*\n{status_label}"),
                block_kit.Markdown(f"*Submitted by*\n{appeal.owner.name}"),
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Order ID*\n{appeal.order.id}"),
                block_kit.Markdown(f"*Appeal ID*\n{appeal.id}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Arbiter :scales:*\n{appeal.order.arbiter.name}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Appeal type*\n{models.AppealType(appeal.type).label}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Appeal reasons*\n{', '.join(appeal.get_reasons())}")
            ])
        ]

        return blocks

    @classmethod
    def get_created_at_block(self, appeal:models.Appeal):
        created_at = appeal.created_at
        if isinstance(created_at, str):
            created_at = datetime.strptime(appeal.created_at, "%Y-%m-%dT%H:%M:%S%z")

        return block_kit.ContextBlock(
            block_kit.Markdown(f"Appeal created {block_kit_helpers.format_timestamp(created_at)}")
        )

class AppealStatusUpdateMessage(MessageBase):
    @classmethod
    def send_safe(cls, *args, **kwargs):
        try:
            return cls.send(*args, **kwargs)
        except Exception as exception:
            logger.exception(exception)
            return exception

    @classmethod
    def send(cls, appeal_id:int, status=None):
        appeal = models.Appeal.objects.filter(id=appeal_id).first()

        if not appeal:
            return

        if not status:
            status = appeal.order.status

        msg_kwargs = cls.build(appeal, status=status.status)
        if not msg_kwargs:
            return

        summary_msgs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.APPEAL_SUMMARY,
            object_id=appeal.id,
            deleted_at__isnull=True,
        ).values("channel", "ts").distinct()

        results = []
        for thread_data in summary_msgs:
            channel = thread_data["channel"]
            thread_ts = str(thread_data["ts"])
            result = dict(channel=channel, thread_ts=thread_ts)

            response = cls.send_message(
                channel=channel,
                thread_ts=thread_ts,
                reply_broadcast=True,
                **msg_kwargs,
            )
            result.update(response)

            if response["success"]:
                models.SlackMessageLog.objects.create(
                    topic=models.SlackMessageLog.Topic.APPEAL_UPDATE,
                    object_id=appeal.id,
                    metadata=dict(status=status.status),
                    channel=response["channel"],
                    ts=response["ts"],
                    thread_ts=thread_ts,
                    deleted_at=None,
                )

            results.append(result)

        return dict(results=results)

    @classmethod
    def build(cls, appeal:models.Appeal, status=None):
        if not status:
            status = appeal.status

        text = cls.get_text(appeal, status=status)

        if not text:
            return

        return dict(
            text=text
        )

    @classmethod
    def get_text(cls, appeal:models.Appeal, status=None):
        if not status:
            status = appeal.order.status
        
        if status == models.StatusType.APPEALED:
            return f"Appeal #{appeal.id} submitted"
        elif status == models.StatusType.RELEASE_PENDING:
            return f"Appeal #{appeal.id} validating release"
        elif status == models.StatusType.REFUND_PENDING:
            return f"Appeal #{appeal.id} validating refund"
        elif status == models.StatusType.RELEASED:
            return f"Appeal #{appeal.id} resolved"
        elif status == models.StatusType.REFUNDED:
            return f"Appeal #{appeal.id} resolved"
        else:
            return ""

class AdSummaryMessage(MessageBase):
    @classmethod
    def send_safe(cls, *args, **kwargs):
        try:
            return cls.send(*args, **kwargs)
        except Exception as exception:
            logger.exception(exception)
            return exception

    @classmethod
    def send(cls, ad_id:int, channel:str=None):
        ad = models.Ad.objects.filter(id=ad_id).first()
        if not ad:
            return

        # Build the message blocks
        blocks = [
            cls.get_message_header_block(ad),
            *cls.get_ad_details_block(ad),
            cls.get_created_at_block(ad)
        ]
        if ad.deleted_at:
            blocks.append(cls.get_deleted_at_block(ad))

        text=f"Ad #{ad.id} Summary"
        attachments = [
            block_kit.Blocks(*blocks),
        ]
        msg_logs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.AD_SUMMARY,
            object_id=ad.id,
            deleted_at__isnull=True,
        )

        send_new = True
        results = []
        for msg_log in msg_logs:
            result = cls.update_message(
                channel=msg_log.channel,
                ts=str(msg_log.ts),
                attachments=attachments,
            )

            if (result["success"] or result.get("error") != "message_not_found") and \
                (not channel or msg_log.channel == channel):
                send_new = False

            results.append(result)

        if send_new:
            kwargs = dict(text=text, attachments=attachments)
            if channel: kwargs["channel"] = channel
            result = cls.send_message(**kwargs)
            results.append(result)

        for result in results:
            if not result.get("success"):
                continue

            models.SlackMessageLog.objects.update_or_create(
                topic=models.SlackMessageLog.Topic.AD_SUMMARY,
                object_id=ad.id,
                channel=result["channel"],
                defaults=dict(
                    ts=result["ts"],
                    deleted_at=None,
                )
            )

        return results

    @classmethod
    def get_message_header_block(cls, ad:models.Ad):
        header_text = f'Ad #{ad.id} Summary'
        plain_text = block_kit.PlainText(header_text)
        header = block_kit.Header(plain_text)
        return header

    @classmethod
    def get_ad_details_block(cls, ad:models.Ad):
        price_type = ad.price_type
        if price_type == models.PriceType.FLOATING:
            floating_price = '{:f}'.format(Decimal(ad.floating_price).normalize())
            price_type = f'{price_type} ({floating_price}%)'

        trade_amount = ad.get_trade_amount()
        trade_amount = '{:f}'.format(Decimal(trade_amount).normalize())
        if ad.trade_amount_in_fiat:
            trade_amount = f'{trade_amount} {ad.fiat_currency.symbol}'
        else:
            trade_amount = f'{trade_amount} {ad.crypto_currency.symbol}'

        trade_floor = ad.get_trade_floor()
        trade_ceiling = ad.get_trade_ceiling()
        trade_floor = '{:f}'.format(Decimal(trade_floor).normalize())
        trade_ceiling = '{:f}'.format(Decimal(trade_ceiling).normalize())
        if ad.trade_limits_in_fiat:
            trade_floor = f'{trade_floor} {ad.fiat_currency.symbol}'
            trade_ceiling = f'{trade_ceiling} {ad.fiat_currency.symbol}' 
        else:
            trade_floor = f'{trade_floor} {ad.crypto_currency.symbol}'
            trade_ceiling = f'{trade_ceiling} {ad.crypto_currency.symbol}'
        
        price = '{:f}'.format(Decimal(ad.get_price()).normalize())
        price = f'{price} {ad.fiat_currency.symbol}'

        visibility = 'Public :loudspeaker:'
        if not ad.is_public:
            visibility = 'Private :dotted_line_face:'

        payment_methods = ad.payment_methods.all()
        payment_type_names = []
        for method in payment_methods:
            payment_type_names.append(method.payment_type.short_name)

        blocks = [            
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Ad ID*\n{ad.id}"),
                block_kit.Markdown(f"*Owner*\n{ad.owner.name}")
            ]),
            block_kit.SectionBlock(
                text=block_kit.Markdown(":page_with_curl: *Price Setting*"),
                fields=[
                    block_kit.Markdown(f"*Price*\n{price}"),
                    block_kit.Markdown(f"*Price Type*\n{price_type}")
                ]
            ),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Currency*\n{ad.fiat_currency.name} ({ad.fiat_currency.symbol})")
            ]),
            block_kit.SectionBlock(
                text=block_kit.Markdown(":page_with_curl: *Trade Settings*"),
                fields=[
                    block_kit.Markdown(f"*Trade Floor*\n{trade_floor}"),
                    block_kit.Markdown(f"*Trade Ceiling*\n{trade_ceiling}")
                ]
            ),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Trade Quantity*\n{trade_amount}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Appealable after*\n{models.CooldownChoices(ad.appeal_cooldown_choice).label}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Visibility*\n{visibility}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Payment Types:*\n{', '.join(payment_type_names)}")
            ])
        ]

        return blocks

    @classmethod
    def get_created_at_block(self, ad:models.Ad):
        created_at = ad.created_at
        if isinstance(created_at, str):
            created_at = datetime.strptime(ad.created_at, "%Y-%m-%dT%H:%M:%S%z")

        return block_kit.ContextBlock(
            block_kit.Markdown(f"Ad created {block_kit_helpers.format_timestamp(created_at)}")
        )
    
    @classmethod
    def get_deleted_at_block(self, ad:models.Ad):
        deleted_at = ad.deleted_at
        if not deleted_at:
            return
        
        if isinstance(deleted_at, str):
            deleted_at = datetime.strptime(ad.deleted_at, "%Y-%m-%dT%H:%M:%S%z")
        
        return block_kit.ContextBlock(
            block_kit.Markdown(f"Ad deleted {block_kit_helpers.format_timestamp(deleted_at)}")
        )


class AdUpdateType(Enum):
    CURRENCY = 'currency'
    PRICE_TYPE = 'price_type'
    FIXED_PRICE = 'fixed_price'
    FLOATING_PRICE = 'floating_price'
    TRADE_FLOOR = 'trade_floor'
    TRADE_CEILING = 'trade_ceiling'
    TRADE_LIMITS_IN_FIAT = 'trade_limits_in_fiat'
    TRADE_AMOUNT = 'trade_amount'
    TRADE_AMOUNT_IN_FIAT = 'trade_amount_in_fiat'
    APPEAL_COOLDOWN = 'appeal_cooldown'
    VISIBILITY = 'visibility'
    PAYMENT_TYPES = 'payment_types'
    DELETED_AT = 'deleted_at'

class AdUpdateMessage(MessageBase):
    @classmethod
    def send_safe(cls, *args, **kwargs):
        try:
            return cls.send(*args, **kwargs)
        except Exception as exception:
            logger.exception(exception)
            return exception

    @classmethod
    def send(cls, ad_id:int, update_type=None, **kwargs):
        ad = models.Ad.objects.filter(id=ad_id).first()

        if not ad:
            return

        if not update_type:
            return

        msg_kwargs = cls.build(ad, update_type=update_type, **kwargs)
        if not msg_kwargs:
            return

        summary_msgs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.AD_SUMMARY,
            object_id=ad.id,
            deleted_at__isnull=True,
        ).values("channel", "ts").distinct()

        results = []
        for thread_data in summary_msgs:
            channel = thread_data["channel"]
            thread_ts = str(thread_data["ts"])
            result = dict(channel=channel, thread_ts=thread_ts)

            response = cls.send_message(
                channel=channel,
                thread_ts=thread_ts,
                reply_broadcast=True,
                **msg_kwargs,
            )
            result.update(response)

            if response["success"]:
                models.SlackMessageLog.objects.create(
                    topic=models.SlackMessageLog.Topic.AD_UPDATE,
                    object_id=ad.id,
                    metadata=dict(update_type=update_type.value),
                    channel=response["channel"],
                    ts=response["ts"],
                    thread_ts=thread_ts,
                    deleted_at=None,
                )

            results.append(result)

        return dict(results=results)

    @classmethod
    def build(cls, ad:models.Ad, update_type=None, **kwargs):
        if not update_type:
            return

        text = cls.get_text(ad, update_type=update_type, context=kwargs.get('context'))

        if not text:
            return

        return dict(
            text=text
        )

    @classmethod
    def get_text(cls, ad:models.Ad, update_type=None, context=None):
        if not update_type:
            return ""

        old_value = context.get('old')
        new_value = context.get('new')

        currency = context.get('currency')
        old_currency = currency
        new_currency = currency

        if currency:
            old_currency = currency.get('old')
            new_currency = currency.get('new')

        if (update_type == AdUpdateType.TRADE_AMOUNT or
            update_type == AdUpdateType.TRADE_FLOOR or
            update_type == AdUpdateType.TRADE_CEILING):
            old_value = satoshi_to_bch(old_value)
            new_value = satoshi_to_bch(new_value)

            if old_currency != 'BCH':
                old_value = bch_to_fiat(old_value, ad.get_price())

            if new_currency != 'BCH':
                new_value = bch_to_fiat(new_value, ad.get_price())

            old_value = '{:f}'.format(old_value.normalize()) if old_currency == 'BCH' else '{:.2f}'.format(old_value.normalize())
            new_value = '{:f}'.format(new_value.normalize()) if new_currency == 'BCH' else '{:.2f}'.format(new_value.normalize())

        if (update_type == AdUpdateType.FIXED_PRICE or
            update_type == AdUpdateType.FLOATING_PRICE):
            old_value = '{:.2f}'.format(old_value)
            new_value = '{:.2f}'.format(new_value)

        if update_type == AdUpdateType.CURRENCY:
            return f"Ad #{ad.id} updated currency from {old_value} to {new_value}"
        elif update_type == AdUpdateType.PRICE_TYPE:
            return f"Ad #{ad.id} updated price type from {old_value} to {new_value}"
        elif update_type == AdUpdateType.FIXED_PRICE:
            return f"Ad #{ad.id} updated fixed price from {old_value} {old_currency or ad.fiat_currency.symbol} to {new_value} {new_currency or ad.fiat_currency.symbol}"
        elif update_type == AdUpdateType.FLOATING_PRICE:
            return f"Ad #{ad.id} updated floating price from {old_value}% to {new_value}%"
        elif update_type == AdUpdateType.TRADE_FLOOR:
            return f"Ad #{ad.id} updated trade floor from {old_value} {old_currency} to {new_value} {new_currency}"
        elif update_type == AdUpdateType.TRADE_CEILING:
            return f"Ad #{ad.id} updated trade ceiling from {old_value} {old_currency} to {new_value} {new_currency}"
        elif update_type == AdUpdateType.TRADE_AMOUNT:
            return f"Ad #{ad.id} updated trade quantity from {old_value} {old_currency} to {new_value} {new_currency}"
        elif update_type == AdUpdateType.TRADE_AMOUNT_IN_FIAT:
            currency = f'{ad.fiat_currency.symbol}' if new_value == True else 'BCH'
            return f"Ad #{ad.id} trade quantity currency set to {currency}"
        elif update_type == AdUpdateType.TRADE_LIMITS_IN_FIAT:
            currency = f'{ad.fiat_currency.symbol}' if new_value == True else 'BCH'
            return f"Ad #{ad.id} trade limits currency set to {currency}"
        elif update_type == AdUpdateType.APPEAL_COOLDOWN:
            old_value = models.CooldownChoices(old_value).label
            new_value = models.CooldownChoices(new_value).label
            return f"Ad #{ad.id} updated appeal cooldown from {old_value} to {new_value}"
        elif update_type == AdUpdateType.VISIBILITY:            
            old_visibility = 'public'
            if not old_value:
                old_visibility = 'private'
            new_visibility = 'public'
            if not new_value:
                new_visibility = 'private' 
            return f"Ad #{ad.id} visibility set from {old_visibility} to {new_visibility}"
        elif update_type == AdUpdateType.PAYMENT_TYPES:
            new_payment_types = ', '.join(new_value) or None
            if new_payment_types == None:
                return ""
            return f"Ad #{ad.id} updated payment type(s) to {new_payment_types}"
        elif update_type == AdUpdateType.DELETED_AT:
            return f"Ad #{ad.id} deleted"
        else:
            return ""