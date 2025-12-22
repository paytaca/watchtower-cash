"""x URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from django.conf.urls import url
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from rest_framework.authtoken import views
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from main.urls import main_urls, test_urls
from paytacapos.urls import urlpatterns as paytacapos_urlpatterns
from smartbch.urls import urlpatterns as sbch_urlpatterns
from anyhedge.urls import urlpatterns as anyhedge_urlpatterns
from notifications.urls import urlpatterns as notifications_urlpatterns
from jpp.urls import urlpatterns as jpp_urlpatterns
from django.conf.urls.static import static
from django.conf import settings
from ramp.urls import urlpatterns as ramp_urlpatterns
from rampp2p.urls import urlpatterns as ramp_p2p_urlpatterns
from paytacagifts.urls import urlpatterns as paytacagifts_urlpatterns
from cts.urls import urlpatterns as cts_urlpatterns
from authentication.urls import urlpatterns as auth_urlpatterns
from stablehedge.urls import urlpatterns as stablehedge_urlpatterns
from multisig.urls import urlpatterns as multisig_urlpatterns
from memos.urls import urlpatterns as memos_urlpatterns

from main.views import TelegramBotView


class CustomOpenAPISchemaGenerator(OpenAPISchemaGenerator):
    def get_operation_id(self, operation_keys):
        """
        Generate operation IDs using URL path components instead of view class names.
        This prevents duplicate operationIds when multiple URLs use the same view.
        
        operation_keys format example: ['api', 'balance', 'ct', '{tokenaddress}', 'get']
        """
        # Extract method (last item)
        method = operation_keys[-1] if operation_keys[-1] in ['get', 'post', 'patch', 'put', 'delete'] else 'get'
        
        # Get path parts (everything except 'api' prefix and method)
        path_parts = []
        for key in operation_keys:
            if key == 'api':
                continue
            if key in ['get', 'post', 'patch', 'put', 'delete']:
                break
            # Handle path parameters like '{tokenaddress}' or 'tokenaddress'
            if key.startswith('{') and key.endswith('}'):
                param_name = key[1:-1]
                # Map parameter names to shorter, clearer names
                param_map = {
                    'tokenaddress': 'ct_addr',
                    'slpaddress': 'slp_addr',
                    'bchaddress': 'bch_addr',
                    'wallethash': 'wallet',
                    'tokenid_or_category': 'token',
                    'category': 'cat',
                    'txid': 'tx',
                    'index': 'idx',
                    'proposal_identifier': 'proposal',
                    'signer_identifier': 'signer',
                    'id': 'id',
                    'shard': 'shard',
                    'address': 'addr',
                    'tokenid': 'token_id',
                }
                path_parts.append(param_map.get(param_name, param_name))
            else:
                path_parts.append(key)
        
        # Create operation_id from path parts
        if path_parts:
            operation_id = '_'.join(path_parts)
            # Clean up: remove any remaining special characters
            operation_id = operation_id.replace('-', '_').replace('/', '_')
            return f"{operation_id}_{method}"
        
        # Fallback to default behavior
        return super().get_operation_id(operation_keys)
    
    def get_operation(self, view, path, prefix, method, components, request, **kwargs):
        """
        Override to ensure we always generate unique operationIds from the path.
        This prevents duplicate operationIds when multiple URLs use the same view.
        """
        operation = super().get_operation(view, path, prefix, method, components, request, **kwargs)
        
        # Always generate operation_id from path to ensure uniqueness
        # Combine prefix and path to get the full path
        full_path = (prefix + path).strip('/')
        path_parts = full_path.split('/')
        # Remove 'api' prefix if present
        if path_parts and path_parts[0] == 'api':
            path_parts = path_parts[1:]
        
        # Process path parts
        processed_parts = []
        for part in path_parts:
            # Handle path parameters
            if part.startswith('{') and part.endswith('}'):
                param_name = part[1:-1]
                # Map parameter names to shorter names
                param_map = {
                    'tokenaddress': 'ct_addr',
                    'slpaddress': 'slp_addr',
                    'bchaddress': 'bch_addr',
                    'wallethash': 'wallet',
                    'tokenid_or_category': 'token',
                    'category': 'cat',
                    'txid': 'tx',
                    'index': 'idx',
                    'proposal_identifier': 'proposal',
                    'signer_identifier': 'signer',
                    'id': 'id',
                    'shard': 'shard',
                    'address': 'addr',
                    'tokenid': 'token_id',
                }
                processed_parts.append(param_map.get(param_name, param_name))
            else:
                processed_parts.append(part.replace('-', '_'))
        
        # Create operation_id
        if processed_parts:
            operation_id = '_'.join(processed_parts)
            operation['operationId'] = f"{operation_id}_{method.lower()}"
        
        return operation


schema_view = get_schema_view(
   openapi.Info(
      title="watchtower",
      default_version='v1',
      description="Instant and reliable infrastructure connecting you to the Bitcoin Cash blockchain",
      contact=openapi.Contact(name="Support",url="https://t.me/WatchTowerCash")
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
   generator_class=CustomOpenAPISchemaGenerator,
)


urlpatterns = [
    path('', TemplateView.as_view(template_name="main/index.html")),
    path(
        '.well-known/apple-app-site-association',
        TemplateView.as_view(
            template_name="main/apple-app-site-association.json",
            content_type="application/json"
        )
    ),
    path(
        '.well-known/assetlinks.json',
        TemplateView.as_view(
            template_name="main/assetlinks.json",
            content_type="application/json"
        )
    ),
    path('admin/', admin.site.urls),
    path('api/', include(main_urls)),
    path('api/smartbch/', include(sbch_urlpatterns)),
    path('api/paytacapos/', include(paytacapos_urlpatterns)),
    path('api/anyhedge/', include(anyhedge_urlpatterns)),
    path('api/push-notifications/', include(notifications_urlpatterns)),
    path('api/jpp/', include(jpp_urlpatterns)),
    path('api/ramp/', include(ramp_urlpatterns)),
    path('api/ramp-p2p/', include(ramp_p2p_urlpatterns)),
    path('api/cts/', include(cts_urlpatterns)),
    path('api/auth/', include(auth_urlpatterns)),
    path('api/stablehedge/', include(stablehedge_urlpatterns)),
    path(r'test/', include(test_urls)),
    path('webhooks/telegram/', csrf_exempt(TelegramBotView.as_view()), name="telegram-webhook"),
    url(r'^api/swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    url(r'^api/redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    url(r'api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    url('api/multisig/', include(multisig_urlpatterns)),
    url('api/memos', include(memos_urlpatterns))
]


urlpatterns += [
    path('api/', include(paytacagifts_urlpatterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    import re
    from django.urls import re_path
    from django.conf import settings
    from rampp2p.views.view_utils import media_proxy_view
    
    base_media_url = settings.MEDIA_URL.strip("/")
    urlpatterns += [
        re_path(r'^'+ re.escape(base_media_url) + r'/(?P<path>.*)$', media_proxy_view),
        path(base_media_url, media_proxy_view),
    ]
