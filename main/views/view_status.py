from django.views import View
from main.utils.queries.node import Node
from django.http import JsonResponse
from django.utils import timezone
from main.models import Wallet, AppVersion
from django.core.exceptions import ObjectDoesNotExist
from packaging.version import Version


NODE = Node()

class StatusView(View):

    def parse_boolean(self, value:str):
        if not isinstance(value, str): return None
        if value.lower() == 'true': return True
        if value.lower() == 'false': return False
        return None

    def detect_platform_from_user_agent(self, user_agent: str) -> str:
        """
        Detect platform from User-Agent string.
        Returns: 'android', 'ios', or 'web'
        """
        if not user_agent:
            return 'web'
        
        user_agent_lower = user_agent.lower()
        
        # Check for Android
        if 'android' in user_agent_lower:
            return 'android'
        
        # Check for iOS (iPhone, iPad, iPod)
        if any(device in user_agent_lower for device in ['iphone', 'ipad', 'ipod']):
            return 'ios'
        
        # Default to web
        return 'web'

    def normalize_version(self, version: str) -> str:
        """
        Remove 'v' prefix from version string if present.
        """
        if not version:
            return version
        return version.lstrip('vV')

    def check_app_version(self, user_version: str, platform: str) -> dict:
        """
        Check user's app version against AppVersion model.
        Returns dict with 'app_version_check' and 'app_upgrade' keys.
        """
        try:
            # Get the latest AppVersion for this platform (ordered by release_date)
            latest_app_version = AppVersion.objects.filter(
                platform=platform
            ).order_by('-release_date').first()
            
            if not latest_app_version:
                return {}
            
            # Normalize user version (remove 'v' prefix)
            normalized_user_version = self.normalize_version(user_version)
            
            # Parse versions using packaging.version for semantic versioning
            try:
                user_ver = Version(normalized_user_version)
                latest_ver = Version(latest_app_version.latest_version)
                min_required_ver = Version(latest_app_version.min_required_version)
            except Exception:
                # If version parsing fails, return empty dict
                return {}
            
            # Determine if user is on latest version
            app_version_check = 'updated' if user_ver >= latest_ver else 'outdated'
            
            result = {
                'app_version_check': app_version_check
            }
            
            # Only include app_upgrade if version is outdated
            if app_version_check == 'outdated':
                # Determine if upgrade is optional or required
                if user_ver >= min_required_ver:
                    app_upgrade = 'optional'
                else:
                    app_upgrade = 'required'
                result['app_upgrade'] = app_upgrade
            
            return result
        except Exception:
            # If any error occurs, return empty dict
            return {}

    def get(self, request):
        response = {'status': 'up', 'health_checks': {}}
        response['timestamp'] = str(timezone.now())

        timestamp_only = self.parse_boolean(request.GET.get('timestamp_only'))
        if timestamp_only:
            del response['health_checks']
            return JsonResponse(response)

        # Capture wallet-hash and paytaca-app-version headers if present
        wallet_hash = request.headers.get('wallet-hash') or request.META.get('HTTP_WALLET_HASH')
        paytaca_app_version = request.headers.get('paytaca-app-version') or request.META.get('HTTP_PAYTACA_APP_VERSION')
        
        if wallet_hash and paytaca_app_version:
            try:
                wallet = Wallet.objects.get(wallet_hash=wallet_hash)
                wallet.paytaca_app_version = paytaca_app_version
                wallet.save(update_fields=['paytaca_app_version'])
            except ObjectDoesNotExist:
                # Wallet not found, silently continue
                pass

        # Check app version if wallet hash and app version are provided
        if wallet_hash and paytaca_app_version:
            user_agent = request.headers.get('User-Agent') or request.META.get('HTTP_USER_AGENT', '')
            platform = self.detect_platform_from_user_agent(user_agent)
            version_check_result = self.check_app_version(paytaca_app_version, platform)
            
            # Add version check results to response if available
            if version_check_result:
                response.update(version_check_result)

        # Test if node is down
        if NODE.BCH.get_latest_block():
            response['health_checks']['node'] = 'up'
        else:
            response['status'] = 'down'
            response['health_checks']['node'] = 'down'
        return JsonResponse(response)
 