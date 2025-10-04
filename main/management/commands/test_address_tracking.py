from django.core.management.base import BaseCommand
from main.utils.redis_address_manager import BCHAddressManager
import logging

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test the Redis address tracking functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--address',
            type=str,
            help='Test with a specific address',
            default='bitcoincash:qtest123456789'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show current tracking statistics',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up expired addresses',
        )

    def handle(self, *args, **options):
        if options['stats']:
            self.show_stats()
        elif options['cleanup']:
            self.cleanup_addresses()
        else:
            self.test_address_tracking(options['address'])

    def test_address_tracking(self, test_address):
        """Test adding, checking, and removing addresses"""
        self.stdout.write(f"Testing address tracking with: {test_address}")
        
        # Test initial state
        initial_count = BCHAddressManager.get_address_count(test_address)
        self.stdout.write(f"Initial connection count: {initial_count}")
        
        # Test adding addresses
        self.stdout.write("\n=== Testing Address Addition ===")
        count1 = BCHAddressManager.add_address(test_address)
        self.stdout.write(f"After first add: {count1} connections")
        
        count2 = BCHAddressManager.add_address(test_address)
        self.stdout.write(f"After second add: {count2} connections")
        
        # Test checking if address is active
        is_active = BCHAddressManager.is_address_active(test_address)
        self.stdout.write(f"Address is active: {is_active}")
        
        # Test getting all active addresses
        active_addresses = BCHAddressManager.get_all_active_addresses()
        self.stdout.write(f"Active addresses: {active_addresses}")
        
        # Test removing addresses
        self.stdout.write("\n=== Testing Address Removal ===")
        count3 = BCHAddressManager.remove_address(test_address)
        self.stdout.write(f"After first remove: {count3} connections")
        
        count4 = BCHAddressManager.remove_address(test_address)
        self.stdout.write(f"After second remove: {count4} connections")
        
        # Test final state
        final_is_active = BCHAddressManager.is_address_active(test_address)
        self.stdout.write(f"Address is still active: {final_is_active}")
        
        final_active_addresses = BCHAddressManager.get_all_active_addresses()
        self.stdout.write(f"Final active addresses: {final_active_addresses}")
        
        self.stdout.write(
            self.style.SUCCESS('Address tracking test completed successfully!')
        )

    def show_stats(self):
        """Show current tracking statistics"""
        stats = BCHAddressManager.get_stats()
        
        self.stdout.write("\n=== Redis Address Tracking Statistics ===")
        self.stdout.write(f"Total active addresses: {stats['total_active_addresses']}")
        self.stdout.write(f"Total connections: {stats['total_connections']}")
        
        if stats['addresses']:
            self.stdout.write("\nActive addresses:")
            for addr in stats['addresses']:
                count = BCHAddressManager.get_address_count(addr)
                self.stdout.write(f"  {addr}: {count} connection(s)")
        else:
            self.stdout.write("No active addresses found.")
        
        self.stdout.write(
            self.style.SUCCESS('Statistics retrieved successfully!')
        )

    def cleanup_addresses(self):
        """Clean up expired addresses"""
        self.stdout.write("Cleaning up expired addresses...")
        
        # Show stats before cleanup
        stats_before = BCHAddressManager.get_stats()
        self.stdout.write(f"Before cleanup: {stats_before['total_active_addresses']} addresses")
        
        # Perform cleanup
        BCHAddressManager.cleanup_expired_addresses()
        
        # Show stats after cleanup
        stats_after = BCHAddressManager.get_stats()
        self.stdout.write(f"After cleanup: {stats_after['total_active_addresses']} addresses")
        
        cleaned = stats_before['total_active_addresses'] - stats_after['total_active_addresses']
        if cleaned > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Cleaned up {cleaned} expired addresses!')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('No expired addresses found to clean up.')
            )
