# Redis Address Tracking System

This system provides real-time tracking of actively listening BCH addresses in Redis, enabling the mempool listener to quickly identify transactions that should be processed with high priority.

## Overview

The system consists of three main components:

1. **BCHAddressManager** (`redis_address_manager.py`) - Utility class for managing address tracking in Redis
2. **Updated WebSocket Consumers** (`consumer.py`) - Track addresses when websockets connect/disconnect
3. **Updated Mempool Listener** (`mempool_listener.py`) - Check Redis for active addresses before processing transactions

## How It Works

### 1. Address Tracking
- When a WebSocket connects to listen to an address, `BCHAddressManager.add_address()` is called
- When a WebSocket disconnects, `BCHAddressManager.remove_address()` is called
- The system maintains both a connection counter (hash) and an active addresses set (set) in Redis

### 2. Redis Data Structure
- **Hash**: `bch:address_consumer_connections_ctr` - Maps address → connection count
- **Set**: `bch:active_listening_addresses` - Contains all addresses with active listeners

### 3. Mempool Processing
- When a new transaction arrives, `_addresses_subscribed()` first checks Redis for active addresses
- If any transaction address has active listeners, it's processed with high priority
- Falls back to database checks for addresses not tracked in Redis

## Key Features

### Performance Benefits
- **Fast Redis lookups** instead of database queries for most address checks
- **Bulk address checking** with `is_any_address_active()` method
- **Automatic cleanup** of expired addresses

### Reliability
- **Connection counting** handles multiple WebSocket connections to the same address
- **Graceful fallback** to database checks when Redis is unavailable
- **Atomic operations** ensure data consistency

### Monitoring
- **Statistics tracking** with `get_stats()` method
- **Cleanup utilities** for maintenance
- **Comprehensive logging** for debugging

## Usage Examples

### Basic Operations
```python
from main.utils.redis_address_manager import BCHAddressManager

# Add an address (when websocket connects)
count = BCHAddressManager.add_address("bitcoincash:qtest123")

# Check if address is active
is_active = BCHAddressManager.is_address_active("bitcoincash:qtest123")

# Remove an address (when websocket disconnects)
remaining = BCHAddressManager.remove_address("bitcoincash:qtest123")
```

### Bulk Operations
```python
# Check multiple addresses at once
addresses = ["bitcoincash:addr1", "bitcoincash:addr2", "bitcoincash:addr3"]
has_active = BCHAddressManager.is_any_address_active(addresses)

# Get all active addresses
active_addresses = BCHAddressManager.get_all_active_addresses()
```

### Monitoring
```python
# Get statistics
stats = BCHAddressManager.get_stats()
print(f"Active addresses: {stats['total_active_addresses']}")
print(f"Total connections: {stats['total_connections']}")

# Cleanup expired addresses
BCHAddressManager.cleanup_expired_addresses()
```

## Testing

Use the management command to test the system:

```bash
# Test basic functionality
python manage.py test_address_tracking

# Show current statistics
python manage.py test_address_tracking --stats

# Clean up expired addresses
python manage.py test_address_tracking --cleanup

# Test with specific address
python manage.py test_address_tracking --address "bitcoincash:qtest123"
```

## Integration Points

### WebSocket Consumers
- **main/consumer.py** - BCH address websocket connections
- **smartbch/consumer.py** - Already has similar Redis tracking for SmartBCH

### Mempool Listener
- **main/management/commands/mempool_listener.py** - Uses Redis for fast address lookups

### Database Models
- **main/models.py** - Address and Subscription models still used for database fallback

## Configuration

The system uses the existing Redis configuration from `settings.py`:
- `REDISKV` - Redis client for key-value operations
- Database number varies by deployment (prod vs dev)

## Maintenance

### Regular Cleanup
Consider running cleanup periodically to remove stale entries:
```python
BCHAddressManager.cleanup_expired_addresses()
```

### Monitoring
Monitor Redis memory usage and connection counts to ensure optimal performance.

## Troubleshooting

### Common Issues
1. **Redis connection errors** - Check Redis configuration in settings
2. **Address not being tracked** - Verify WebSocket consumer is calling add_address()
3. **Stale addresses** - Run cleanup to remove expired entries

### Debug Commands
```bash
# Check Redis keys directly
redis-cli KEYS "bch:*"

# View active addresses
redis-cli SMEMBERS "bch:active_listening_addresses"

# Check connection counts
redis-cli HGETALL "bch:address_consumer_connections_ctr"
```
