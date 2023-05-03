"""
ASGI config for x project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchtower.settings')
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from channels.routing import ProtocolTypeRouter, URLRouter
import main.routing
import anyhedge.routing
import rampp2p.routing

application = ProtocolTypeRouter({
  "http": django_asgi_app,
  "websocket": AllowedHostsOriginValidator(
    AuthMiddlewareStack(
        URLRouter(
          anyhedge.routing.websocket_urlpatterns +
          main.routing.websocket_urlpatterns +
          rampp2p.routing.websocket_urlpatterns
        )
    )
  )
})
