#!/usr/bin/env python3
"""
Example Python client for listening to JPP invoice payment updates via WebSocket.

Usage:
    python websocket_client_example.py <invoice_uuid>

Example:
    python websocket_client_example.py 1234567890abcdef1234567890abcdef

Requirements:
    pip install websocket-client
"""

import sys
import json
import websocket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def on_message(ws, message):
    """Handle incoming WebSocket messages."""
    data = json.loads(message)
    logger.info("=" * 60)
    logger.info("PAYMENT UPDATE RECEIVED!")
    logger.info("=" * 60)
    logger.info(f"Type: {data.get('type')}")
    logger.info(f"Transaction ID: {data.get('txid')}")
    logger.info(f"Paid At: {data.get('paid_at')}")
    if data.get('memo'):
        logger.info(f"Memo: {data.get('memo')}")
    
    invoice = data.get('invoice', {})
    if invoice:
        logger.info(f"\nInvoice Details:")
        logger.info(f"  Payment ID: {invoice.get('payment_id')}")
        logger.info(f"  Network: {invoice.get('network')}")
        logger.info(f"  Currency: {invoice.get('currency')}")
        logger.info(f"  Total BCH: {invoice.get('payment', {}).get('total_bch', 'N/A')}")
    
    logger.info("=" * 60)


def on_error(ws, error):
    """Handle WebSocket errors."""
    logger.error(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket connection close."""
    logger.info(f"WebSocket connection closed (status: {close_status_code}, msg: {close_msg})")


def on_open(ws):
    """Handle WebSocket connection open."""
    logger.info("WebSocket connection established")
    logger.info("Listening for payment updates...")


def main():
    if len(sys.argv) < 2:
        print("Usage: python websocket_client_example.py <invoice_uuid>")
        print("Example: python websocket_client_example.py 1234567890abcdef1234567890abcdef")
        sys.exit(1)
    
    invoice_uuid = sys.argv[1]
    
    # Default to local development, change to your server URL
    host = sys.argv[2] if len(sys.argv) > 2 else "localhost:8000"
    protocol = "wss" if "watchtower.cash" in host else "ws"
    
    ws_url = f"{protocol}://{host}/ws/jpp/invoice/{invoice_uuid}/"
    
    logger.info(f"Connecting to: {ws_url}")
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Run forever
    ws.run_forever()


if __name__ == "__main__":
    main()

