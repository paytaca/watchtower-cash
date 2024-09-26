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
            cls.get_order_details_block(order),
            # cls.get_summary_block(order),
            cls.get_created_at_block(order),
        ]

        # env_block = cls.get_env_context_block()
        # if env_block: blocks.append(env_block)

        text=f"Order #{order.id} Summary"
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
                text=text,
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
            # result = {"ts": "1714462947.129919", "channel": "C018JFHNXPS" }
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
        return block_kit_helpers.resolve_color_from_order_status(order.status)

    @classmethod
    def get_order_details_block(cls, order:models.Order):
        try:
            status_label = models.StatusType(order.status).label
        except ValueError:
            status_label = order.status.replace("_", " ").capitalize()

        fields = [
            block_kit.Markdown(f"*Status*\n {status_label}"),
            block_kit.Markdown(f"*Created by*\n{order.owner.name}"),
        ]

        return block_kit.SectionBlock(*fields)

    # @classmethod
    # def get_summary_block(cls, order:connecta_models.Order):
    #     currency = order.currency.symbol
    #     markup_subtotal = order.markup_subtotal or 0
    #     subtotal = order.subtotal or 0
    #     markup_amount = markup_subtotal - subtotal
    #     delivery_fee = order.payment.delivery_fee or 0
    #     total = float(markup_subtotal) + float(delivery_fee)
    #     return block_kit.SectionBlock(
    #         text=block_kit.Markdown(":page_with_curl: *Summary:*"),
    #         fields=[
    #             block_kit.Markdown(f"*Subtotal*\n{subtotal:.2f} {currency}"),
    #             block_kit.Markdown(f"*Markup*\n{markup_amount:.2f} {currency}"),
    #             block_kit.Markdown(f"*Delivery*\n{delivery_fee:.2f} {currency}"),
    #             block_kit.Markdown(f"*Total*\n{total:.2f} {currency}"),
    #         ]
    #     )

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
            last_status = models.Status.objects.filter(order__id=order_id).order_by('-created_at').first()
            status = order.status

        msg_kwargs = cls.build(order, status=status)
        if not msg_kwargs:
            return

        summary_msgs = models.SlackMessageLog.objects.filter(
            topic=models.SlackMessageLog.Topic.ORDER_SUMMARY,
            object_id=order.id,
            deleted_at__isnull=True,
        ).values("channel", "ts").distinct()


        slack_msg_obj_data = dict(
            topic=models.SlackMessageLog.Topic.ORDER_STATUS_UPDATE,
            object_id=order.id,
            metadata=dict(status=status),
        )

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
                obj = models.SlackMessageLog.objects.create(
                    topic=models.SlackMessageLog.Topic.ORDER_STATUS_UPDATE,
                    object_id=order.id,
                    metadata=dict(status=status),
                    channel=response["channel"],
                    ts=response["ts"],
                    thread_ts=thread_ts,
                    deleted_at=None,
                )

            results.append(result)

        return dict(results=results)

    @classmethod
    def build(cls, order:connecta_models.Order, status=None):
        if not status:
            status = order.status

        text = cls.get_text(order, status=status)

        if not text:
            return

        context_block = cls.get_context_block(order, status=status)
        blocks = []

        cancel_reason_block = None
        if status == order.Status.CANCELLED:
            cancel_reason_block = cls.get_cancel_reason_block(order)

        if cancel_reason_block: blocks.append(cancel_reason_block)
        if context_block: blocks.append(context_block)

        return dict(
            text=text,
            attachments=[dict(
                color=cls.resolve_color_from_status(status),
                blocks=blocks,
            )],
        )

    @classmethod
    def resolve_color_from_status(cls, status:str):
        return block_kit_helpers.resolve_color_from_order_status(status)

    @classmethod
    def get_cancel_reason_block(cls, order:connecta_models.Order):
        if not order.cancel_reason:
            return

        return block_kit.SectionBlock(
            block_kit.Markdown(f"Reason: \n{order.cancel_reason}")
        )

    @classmethod
    def get_context_block(cls, order:connecta_models.Order, status=None):
        if not status:
            status = order.status

        update_obj = order.updates \
            .filter(new_value__status=status) \
            .order_by("-created_at") \
            .first()

        if not update_obj: return None

        timestamp_obj = update_obj.created_at
        if isinstance(timestamp_obj, str):
            timestamp_obj = datetime.strptime(timestamp_obj, "%Y-%m-%dT%H:%M:%S%z")

        timestamp = int(timestamp_obj.timestamp())
        timestamp_text = f" {block_kit_helpers.format_timestamp(timestamp_obj)}"

        name_text = ""
        if update_obj.created_by:
            full_name = f"{update_obj.created_by.first_name} {update_obj.created_by.last_name}".strip()
            if full_name:
                name_text = f" by {full_name}"

        text = f"Updated{timestamp_text}{name_text}"
        return block_kit.ContextBlock(block_kit.Markdown(text))

    @classmethod
    def get_text(cls, order:connecta_models.Order, status=None):
        if not status:
            status = order.status
        
        if status == order.Status.PENDING:
            return f"Pending Order #{order.id}"
        elif status == order.Status.CONFIRMED:
            return f"Order #{order.id} is confirmed"
        elif status == order.Status.PREPARING:
            return f"Order #{order.id} is being prepared"
        elif status == order.Status.PICKUP:
            return f"Order #{order.id} is ready for pickup"
        elif status == order.Status.PICKED_UP:
            return f"Order #{order.id} has been picked up"
        elif status == order.Status.ON_DELIVERY:
            return f"Order #{order.id} is being delivered"
        elif status == order.Status.DELIVERED:
            return f"Order #{order.id} has been delivered"
        elif status == order.Status.COMPLETED:
            return f"Order #{order.id} is completed"
        elif status == order.Status.CANCELLED:
            return f"Order #{order.id} is cancelled"
        else:
            return ""
