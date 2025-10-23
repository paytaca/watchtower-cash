from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import json
import logging


logger = logging.getLogger(__name__)


class InvoicePaymentConsumer(WebsocketConsumer):
    """
    WebSocket consumer for listening to JPP invoice payment updates.
    Clients can connect to ws/jpp/invoice/{invoice_uuid}/ to receive real-time updates
    when a payment is made to the invoice.
    
    SECURITY: This consumer is READ-ONLY. It does not implement receive() or receive_json()
    to prevent clients from sending fake transaction updates that could be relayed to others.
    Only server-side code can trigger notifications via channel_layer.group_send().
    """

    def connect(self):
        self.invoice_uuid = self.scope['url_route']['kwargs'].get('invoice_uuid')
        
        if self.invoice_uuid:
            self.room_name = f"jpp_invoice_{self.invoice_uuid}"
            logger.info(f"WS WATCH FOR JPP INVOICE {self.invoice_uuid} CONNECTED!")
            
            async_to_sync(self.channel_layer.group_add)(
                self.room_name,
                self.channel_name
            )
            
            self.accept()
        else:
            logger.warning("WebSocket connection rejected: No invoice UUID provided")
            self.close()

    def disconnect(self, close_code):
        if self.invoice_uuid:
            logger.info(f"WS WATCH FOR JPP INVOICE {self.invoice_uuid} DISCONNECTED!")
            
            async_to_sync(self.channel_layer.group_discard)(
                self.room_name,
                self.channel_name
            )
        
    def send_update(self, event):
        """
        Handler for send_update event type.
        Sends the payment data to the WebSocket client.
        """
        logger.info(f'SENDING JPP INVOICE UPDATE: {event}')
        data = event.get('data', {})
        self.send(text_data=json.dumps(data))

