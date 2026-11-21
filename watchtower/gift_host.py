"""Keep the public gift hostname on its own restricted URL configuration."""
from django.http.request import split_domain_port


class GiftHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        domain, _ = split_domain_port(request.get_host())
        if domain == 'gifts.paytaca.com':
            request.urlconf = 'paytacagifts.public_urls'
        return self.get_response(request)
