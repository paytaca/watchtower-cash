from slack import WebClient
from slack.errors import SlackApiError
from django.conf import settings
from django.utils import timezone
from datetime import datetime

from . import block_kit
from . import block_kit_helpers

import rampp2p.models as models
import logging
logger = logging.getLogger(__name__)

class MessageBase(object):
    @classmethod
    def get_client(cls, token=settings.SLACK_BOT_USER_TOKEN):
        return WebClient(token=token)

    @classmethod
    def update_message(cls, channel=settings.SLACK_CHANNEL, ts="", text=None, blocks=[], attachments=[]):
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
    def send_message(cls, channel=settings.SLACK_CHANNEL, text=None, blocks=[], attachments=[], thread_ts=None, reply_broadcast=False):
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
        trade_amount = '{:.10f}'.format(float(str(order.crypto_amount))).rstrip('0').rstrip('.')
        fiat_trade_amount = '{:.2f}'.format(order.crypto_amount * ad_price)

        blocks = [
            block_kit.SectionBlock(
                text=block_kit.Markdown(":page_with_curl: *Trade Summary:*"),
                fields=[
                    block_kit.Markdown(f"*Ad Owner*\n{ad_owner}"),
                    block_kit.Markdown(f"*Ad Price*\n{ad_price:.2f} {currency}")
                ]
            ),
            block_kit.SectionBlock(block_kit.Markdown(f"*Trade Amount*\n{trade_amount} BCH ({fiat_trade_amount} {currency})"))
        ]
        return blocks

    @classmethod
    def get_created_at_block(self, order:models.Order):
        created_at = order.created_at
        if isinstance(created_at, str):
            created_at = datetime.strptime(order.created_at, "%Y-%m-%dT%H:%M:%S%z")

        return block_kit.ContextBlock(
            block_kit.Markdown(f"Order created at {block_kit_helpers.format_timestamp(created_at)}")
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
    def resolve_color_from_status(cls, status:str):
        return block_kit_helpers.resolve_color_from_order_status(status)

    @classmethod
    def get_text(cls, order:models.Order, status=None):
        if not status:
            status = order.status
        
        if status == models.StatusType.SUBMITTED:
            return f"Order #{order.id} submitted"
        elif status == models.StatusType.CONFIRMED:
            return f"Order #{order.id} confirmed"
        elif status == models.StatusType.ESCROW_PENDING:
            return f"Order #{order.id} waiting for escrow"
        elif status == models.StatusType.ESCROWED:
            return f"Order #{order.id} escrowed"
        elif status == models.StatusType.PAID_PENDING:
            return f"Order #{order.id} fiat payment awaiting confirmation"
        elif status == models.StatusType.PAID:
            return f"Order #{order.id} fiat payment confirmed"
        elif status == models.StatusType.APPEALED:
            return f"Order #{order.id} appealed"
        elif status == models.StatusType.RELEASED:
            return f"Order #{order.id} released"
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
    def resolve_color_from_status(cls, appeal: models.Appeal):
        return block_kit_helpers.resolve_color_from_appeal_status(appeal.order.status.status)

    @classmethod
    def resolve_status(cls, appeal:models.Appeal):
        status = 'Pending'
        if appeal.resolved_at:
            order_status = appeal.order.status.status
            if order_status == models.StatusType.REFUND_PENDING:
                status = models.StatusType.REFUNDED.label
            elif order_status == models.StatusType.RELEASE_PENDING:
                status = models.StatusType.RELEASED.label
        logger.warning(f'status: {status}')
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
                block_kit.Markdown(f"*Appeal ID*\n{appeal.id}")
            ]),
            block_kit.SectionBlock(*[
                block_kit.Markdown(f"*Created by*\n{appeal.owner.name}"),
                block_kit.Markdown(f"*Order ID*\n{appeal.order.id}")
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