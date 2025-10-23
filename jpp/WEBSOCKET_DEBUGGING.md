# JPP WebSocket Debugging Guide

## Common Issues and Solutions

### Issue: "There was a bad response from the server"

This error typically means the WebSocket upgrade request failed. Here are the most common causes:

### 1. **Server Not Restarted (Most Common)**

The new JPP routing code needs to be loaded by restarting the server.

**Solution:**
```bash
# If using supervisor (production)
supervisorctl restart webserver

# Or restart all services
supervisorctl restart all

# If using docker-compose
docker-compose restart

# If running locally
# Stop the server (Ctrl+C) and restart it
python manage.py runserver
```

### 2. **Code Not Deployed**

The changes need to be on the production server.

**Check if code is deployed:**
```bash
# SSH to server and check if files exist
ls -la /code/jpp/consumer.py
ls -la /code/jpp/routing.py
ls -la /code/jpp/utils/websocket.py
```

**Deploy:**
```bash
# Pull latest code
git pull origin master

# Restart services
supervisorctl restart webserver
```

### 3. **Import Error**

There might be a Python import error preventing the module from loading.

**Check logs:**
```bash
# Check supervisor logs
tail -f /var/log/supervisor/webserver-stdout*.log
tail -f /var/log/supervisor/webserver-stderr*.log

# Check if jpp.routing can be imported
python manage.py shell
>>> import jpp.routing
>>> print(jpp.routing.websocket_urlpatterns)
```

### 4. **Invalid Invoice UUID**

The invoice might not exist or UUID format is incorrect.

**Verify invoice exists:**
```bash
python manage.py shell
>>> from jpp.models import Invoice
>>> invoice_uuid = '6f6aaa522ab0428d9b40df84e216e80c'
>>> Invoice.objects.filter(uuid=invoice_uuid).exists()
```

**Check UUID format:**
- Should be 32 hexadecimal characters (no hyphens)
- Example: `6f6aaa522ab0428d9b40df84e216e80c`

### 5. **ASGI Application Not Loading**

The ASGI configuration might have an error.

**Test ASGI:**
```bash
python manage.py shell
>>> from watchtower import asgi
>>> print(asgi.application)
>>> import jpp.routing
>>> print(jpp.routing.websocket_urlpatterns)
```

### 6. **Nginx Configuration**

Nginx needs to proxy WebSocket connections properly.

**Check nginx config:**
```bash
# Verify nginx is proxying /ws/ correctly
cat /etc/nginx/sites-enabled/watchtower

# Should have:
# location /ws/ {
#     proxy_pass http://127.0.0.1:9000;  # or port 8000 if using daphne
#     proxy_http_version 1.1;
#     proxy_set_header Upgrade $http_upgrade;
#     proxy_set_header Connection "upgrade";
# }
```

### 7. **Port Mismatch**

Check if nginx is proxying to the correct backend port.

**In `supervisord.conf`:**
- WebSocket server: `uvicorn --port 9000`

**In `supervisor/webserver.conf` (production):**
- Uses Daphne: `daphne -p 8000`

**Verify nginx proxies to correct port:**
```bash
# Check which port Daphne is listening on
netstat -tulpn | grep daphne
# or
ps aux | grep daphne
```

## Quick Diagnostic Script

Create and run this script to diagnose the issue:

```python
#!/usr/bin/env python
# diagnostic.py

import os
import sys
import django

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
    print(f"   {file_path}: {'✓' if exists else '✗ MISSING'}")

# 2. Check if modules can be imported
print("\n2. Checking if modules can be imported...")
try:
    import jpp.consumer
    print("   jpp.consumer: ✓")
except Exception as e:
    print(f"   jpp.consumer: ✗ ERROR - {e}")

try:
    import jpp.routing
    print("   jpp.routing: ✓")
except Exception as e:
    print(f"   jpp.routing: ✗ ERROR - {e}")

try:
    from jpp.utils import websocket
    print("   jpp.utils.websocket: ✓")
except Exception as e:
    print(f"   jpp.utils.websocket: ✗ ERROR - {e}")

# 3. Check URL patterns
print("\n3. Checking URL patterns...")
try:
    import jpp.routing
    patterns = jpp.routing.websocket_urlpatterns
    print(f"   Found {len(patterns)} pattern(s)")
    for pattern in patterns:
        print(f"   - {pattern.pattern}")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

# 4. Check ASGI configuration
print("\n4. Checking ASGI configuration...")
try:
    from watchtower import asgi
    print("   ASGI application: ✓")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

# 5. Check if test invoice exists
print("\n5. Checking test invoice...")
try:
    from jpp.models import Invoice
    test_uuid = '6f6aaa522ab0428d9b40df84e216e80c'
    exists = Invoice.objects.filter(uuid=test_uuid).exists()
    print(f"   Invoice {test_uuid}: {'✓ EXISTS' if exists else '✗ NOT FOUND'}")
    
    if not exists:
        print("\n   Available invoices:")
        for inv in Invoice.objects.all()[:5]:
            print(f"   - {inv.uuid.hex}")
except Exception as e:
    print(f"   ✗ ERROR - {e}")

print("\n=== Diagnostic Complete ===")
```

**Run it:**
```bash
python diagnostic.py
```

## Testing Locally

To test if the WebSocket works locally:

```bash
# 1. Start the development server
python manage.py runserver

# 2. In another terminal, test the WebSocket
python jpp/examples/websocket_client_example.py <invoice_uuid> localhost:8000

# 3. Create a test invoice
curl -X POST http://localhost:8000/jpp/invoices/ \
  -H "Content-Type: application/json" \
  -d '{
    "outputs": [{"amount": 10000, "address": "bitcoincash:qp..."}],
    "memo": "Test"
  }'

# 4. Note the payment_id from response, then connect WebSocket
python jpp/examples/websocket_client_example.py <payment_id> localhost:8000
```

## Production Deployment Checklist

- [ ] Code changes committed and pushed to repository
- [ ] Code pulled on production server
- [ ] No Python syntax errors (check with `python -m py_compile jpp/*.py`)
- [ ] Imports work (test with `python -c "import jpp.routing"`)
- [ ] Webserver restarted (`supervisorctl restart webserver`)
- [ ] Check logs for errors (`tail -f /var/log/supervisor/webserver-stderr*.log`)
- [ ] Test WebSocket connection
- [ ] Verify invoice exists

## Expected Behavior

When working correctly:

1. **Connection logs:**
   ```
   [jpp] WS WATCH FOR JPP INVOICE 6f6aaa522ab0428d9b40df84e216e80c CONNECTED!
   ```

2. **Payment logs:**
   ```
   [jpp] Sending WebSocket update for invoice 6f6aaa522ab0428d9b40df84e216e80c, txid: abc123...
   [jpp] WebSocket notification sent for invoice 6f6aaa522ab0428d9b40df84e216e80c
   ```

3. **Client receives message:**
   ```json
   {
     "type": "payment_received",
     "txid": "abc123...",
     "paid_at": "2025-10-23T...",
     ...
   }
   ```

## Still Not Working?

If none of the above helps, provide:

1. **Server logs:**
   ```bash
   tail -100 /var/log/supervisor/webserver-stderr*.log
   ```

2. **Import test:**
   ```bash
   python manage.py shell
   >>> import jpp.routing
   >>> print(jpp.routing.websocket_urlpatterns)
   ```

3. **WebSocket test from server:**
   ```bash
   # Install wscat if needed: npm install -g wscat
   wscat -c ws://localhost:8000/ws/jpp/invoice/6f6aaa522ab0428d9b40df84e216e80c/
   ```

4. **Django version and channels version:**
   ```bash
   python -c "import django; print(django.VERSION)"
   python -c "import channels; print(channels.__version__)"
   ```

