from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging


logger = logging.getLogger(__name__)


def send_invoice_payment_update(invoice_obj, payment_obj):
    """
    Send WebSocket notification when a payment is made to an invoice.
    
    Args:
        invoice_obj: The Invoice instance that was paid
        payment_obj: The InvoicePayment instance created
    """
    from jpp.serializers import InvoiceSerializer
    
    channel_layer = get_channel_layer()
    room_name = f"jpp_invoice_{invoice_obj.uuid.hex}"
    
    # Prepare the data to send - include full invoice details with payment info
    try:
        serializer = InvoiceSerializer(invoice_obj)
        data = {
            'type': 'payment_received',
            'invoice': serializer.data,
            'txid': payment_obj.txid,
            'paid_at': str(payment_obj.paid_at),
            'memo': payment_obj.memo,
        }
        
        logger.info(f"Sending WebSocket update for invoice {invoice_obj.uuid.hex}, txid: {payment_obj.txid}")
        
        async_to_sync(channel_layer.group_send)(
            room_name,
            {
                "type": "send_update",
                "data": data
            }
        )
        
        logger.info(f"WebSocket notification sent for invoice {invoice_obj.uuid.hex}")
    except Exception as e:
        logger.error(f"Error sending WebSocket notification for invoice {invoice_obj.uuid.hex}: {str(e)}")

