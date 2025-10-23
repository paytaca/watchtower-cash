#!/usr/bin/env python
"""
JPP WebSocket diagnostic script.
Run this to check if the WebSocket implementation is properly set up.

Usage:
    python jpp/diagnostic.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchtower.settings')
django.setup()

print("=== JPP WebSocket Diagnostic ===\n")

# 1. Check if files exist
print("1. Checking if new files exist...")
files_to_check = [
    'jpp/consumer.py',
    'jpp/routing.py',
    'jpp/utils/websocket.py',
]
for file_path in files_to_check:
    exists = os.path.exists(file_path)
    status = '✓' if exists else '✗ MISSING'
    print(f"   {file_path}: {status}")

# 2. Check if modules can be imported
print("\n2. Checking if modules can be imported...")
try:
    import jpp.consumer
    print("   jpp.consumer: ✓")
except Exception as e:
    print(f"   jpp.consumer: ✗ ERROR - {e}")
    sys.exit(1)

try:
    import jpp.routing
    print("   jpp.routing: ✓")
except Exception as e:
    print(f"   jpp.routing: ✗ ERROR - {e}")
    sys.exit(1)

try:
    from jpp.utils import websocket
    print("   jpp.utils.websocket: ✓")
except Exception as e:
    print(f"   jpp.utils.websocket: ✗ ERROR - {e}")
    sys.exit(1)

# 3. Check URL patterns
print("\n3. Checking URL patterns...")
try:
    import jpp.routing
    patterns = jpp.routing.websocket_urlpatterns
    print(f"   Found {len(patterns)} WebSocket pattern(s)")
    for pattern in patterns:
        print(f"   - Pattern: {pattern.pattern}")
        print(f"     Regex: {pattern.pattern.regex.pattern}")
except Exception as e:
    print(f"   ✗ ERROR - {e}")
    sys.exit(1)

# 4. Check ASGI configuration
print("\n4. Checking ASGI configuration...")
try:
    from watchtower import asgi
    print("   ASGI application: ✓")
    
    # Check if jpp routing is included
    print("   Checking if JPP routing is in ASGI config...")
    asgi_source = open('watchtower/asgi.py').read()
    if 'jpp.routing' in asgi_source:
        print("   JPP routing included in ASGI: ✓")
    else:
        print("   JPP routing included in ASGI: ✗ NOT FOUND")
        print("   Add 'import jpp.routing' and include websocket_urlpatterns")
except Exception as e:
    print(f"   ✗ ERROR - {e}")
    sys.exit(1)

# 5. Check if any invoices exist
print("\n5. Checking invoices...")
try:
    from jpp.models import Invoice
    count = Invoice.objects.count()
    print(f"   Total invoices in database: {count}")
    
    if count > 0:
        print("\n   Recent invoices (showing up to 5):")
        for inv in Invoice.objects.order_by('-time')[:5]:
            status = "PAID" if hasattr(inv, 'payment') and inv.payment else "UNPAID"
            print(f"   - UUID: {inv.uuid.hex} ({status})")
            print(f"     Created: {inv.time}")
            print(f"     Expires: {inv.expires}")
    else:
        print("   No invoices found. Create one to test:")
        print("   POST /jpp/invoices/ with outputs data")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

# 6. Test consumer initialization
print("\n6. Testing consumer initialization...")
try:
    from jpp.consumer import InvoicePaymentConsumer
    consumer = InvoicePaymentConsumer()
    print("   InvoicePaymentConsumer instantiation: ✓")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

# 7. Check channel layers
print("\n7. Checking channel layers configuration...")
try:
    from django.conf import settings
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    if channel_layer:
        print(f"   Channel layer configured: ✓")
        print(f"   Backend: {channel_layer.__class__.__name__}")
    else:
        print("   Channel layer: ✗ NOT CONFIGURED")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

# 8. Check logger configuration
print("\n8. Checking logger configuration...")
try:
    import logging
    logger = logging.getLogger('jpp')
    print(f"   JPP logger configured: ✓")
    print(f"   Log level: {logging.getLevelName(logger.level)}")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

print("\n=== Diagnostic Complete ===")
print("\nIf all checks passed, the WebSocket implementation is properly set up.")
print("Make sure to restart the server to load the new code!")
print("\nTo test:")
print("1. Restart server: supervisorctl restart webserver")
print("2. Run client: python jpp/examples/websocket_client_example.py <invoice_uuid>")

