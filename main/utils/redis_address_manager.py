import logging
from django.conf import settings

LOGGER = logging.getLogger(__name__)
REDIS_CLIENT = settings.REDISKV

_REDIS_NAME__BCH_ADDRESS_CONNECTIONS_CTR = "bch:address_consumer_connections_ctr"
_REDIS_NAME__BCH_ACTIVE_ADDRESSES = "bch:active_listening_addresses"


class BCHAddressManager:
    """
    Manages actively listening BCH addresses in Redis.
    Tracks both connection counts and maintains a set of active addresses.
    """
    
    @classmethod
    def add_address(cls, address):
        """
        Add an address to the actively listening set and increment connection count.
        
        Args:
            address (str): The BCH address to track
            
        Returns:
            int: The current connection count for this address
        """
        if not address:
            return 0
            
        # Increment connection counter
        count = REDIS_CLIENT.hincrby(_REDIS_NAME__BCH_ADDRESS_CONNECTIONS_CTR, address, 1)
        
        # Add to active addresses set if this is the first connection
        if count == 1:
            REDIS_CLIENT.sadd(_REDIS_NAME__BCH_ACTIVE_ADDRESSES, address)
            LOGGER.info(f"Address {address} added to active listening addresses")
        
        LOGGER.info(f"Address {address} now has {count} websocket connection(s)")
        return count
    
    @classmethod
    def remove_address(cls, address):
        """
        Remove an address from tracking and decrement connection count.
        
        Args:
            address (str): The BCH address to stop tracking
            
        Returns:
            int: The remaining connection count for this address (0 if removed)
        """
        if not address:
            return 0
            
        # Decrement connection counter
        count = REDIS_CLIENT.hincrby(_REDIS_NAME__BCH_ADDRESS_CONNECTIONS_CTR, address, -1)
        
        # Remove from active addresses set if no more connections
        if count <= 0:
            REDIS_CLIENT.hdel(_REDIS_NAME__BCH_ADDRESS_CONNECTIONS_CTR, address)
            REDIS_CLIENT.srem(_REDIS_NAME__BCH_ACTIVE_ADDRESSES, address)
            LOGGER.info(f"Address {address} removed from active listening addresses")
            return 0
        
        LOGGER.info(f"Address {address} now has {count} websocket connection(s) remaining")
        return count
    
    @classmethod
    def get_address_count(cls, address):
        """
        Get the number of connections listening to an address.
        
        Args:
            address (str): The BCH address to check
            
        Returns:
            int: Number of connections, or 0 if not tracked
        """
        if not address:
            return 0
            
        try:
            value = REDIS_CLIENT.hget(_REDIS_NAME__BCH_ADDRESS_CONNECTIONS_CTR, address)
            if value is None:
                return 0
            return int(value)
        except (ValueError, TypeError):
            # Clean up invalid entry
            REDIS_CLIENT.hdel(_REDIS_NAME__BCH_ADDRESS_CONNECTIONS_CTR, address)
            REDIS_CLIENT.srem(_REDIS_NAME__BCH_ACTIVE_ADDRESSES, address)
            return 0
    
    @classmethod
    def is_address_active(cls, address):
        """
        Check if an address is actively being listened to.
        
        Args:
            address (str): The BCH address to check
            
        Returns:
            bool: True if address has active listeners, False otherwise
        """
        return cls.get_address_count(address) > 0
    
    @classmethod
    def get_all_active_addresses(cls):
        """
        Get all addresses that are currently being listened to.
        
        Returns:
            set: Set of all active BCH addresses
        """
        try:
            addresses = REDIS_CLIENT.smembers(_REDIS_NAME__BCH_ACTIVE_ADDRESSES)
            return {addr.decode('utf-8') for addr in addresses} if addresses else set()
        except Exception as e:
            LOGGER.error(f"Error getting active addresses: {e}")
            return set()
    
    @classmethod
    def is_any_address_active(cls, addresses):
        """
        Check if any of the provided addresses are actively being listened to.
        
        Args:
            addresses (list): List of BCH addresses to check
            
        Returns:
            bool: True if any address has active listeners, False otherwise
        """
        if not addresses:
            return False
            
        try:
            # Use individual SISMEMBER checks (compatible with older Redis versions)
            for address in addresses:
                if REDIS_CLIENT.sismember(_REDIS_NAME__BCH_ACTIVE_ADDRESSES, address):
                    return True
            return False
        except Exception as e:
            LOGGER.error(f"Error checking address activity: {e}")
            # Fallback to individual checks using get_address_count
            for address in addresses:
                if cls.is_address_active(address):
                    return True
            return False
    
    @classmethod
    def cleanup_expired_addresses(cls):
        """
        Clean up any addresses that have zero connections but are still in the active set.
        This is a maintenance function that can be called periodically.
        """
        try:
            active_addresses = cls.get_all_active_addresses()
            cleaned_count = 0
            
            for address in active_addresses:
                count = cls.get_address_count(address)
                if count == 0:
                    REDIS_CLIENT.srem(_REDIS_NAME__BCH_ACTIVE_ADDRESSES, address)
                    cleaned_count += 1
            
            if cleaned_count > 0:
                LOGGER.info(f"Cleaned up {cleaned_count} expired addresses from active set")
                
        except Exception as e:
            LOGGER.error(f"Error during cleanup: {e}")
    
    @classmethod
    def get_stats(cls):
        """
        Get statistics about tracked addresses.
        
        Returns:
            dict: Statistics including total active addresses and connection counts
        """
        try:
            active_addresses = cls.get_all_active_addresses()
            total_connections = sum(cls.get_address_count(addr) for addr in active_addresses)
            
            return {
                'total_active_addresses': len(active_addresses),
                'total_connections': total_connections,
                'addresses': list(active_addresses)
            }
        except Exception as e:
            LOGGER.error(f"Error getting stats: {e}")
            return {
                'total_active_addresses': 0,
                'total_connections': 0,
                'addresses': []
            }
