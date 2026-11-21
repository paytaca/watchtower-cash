"""Routes exposed through gifts.paytaca.com, excluding other Watchtower APIs."""
from django.urls import include, path
from django.views.generic import TemplateView

from paytacagifts.views.home import GiftClaimView


urlpatterns = [
    path('api/', include('paytacagifts.urls')),
    path('claim', GiftClaimView.as_view()),
    path('claim/', GiftClaimView.as_view()),
    path('.well-known/apple-app-site-association', TemplateView.as_view(
        template_name='main/apple-app-site-association.json',
        content_type='application/json',
    )),
    path('.well-known/assetlinks.json', TemplateView.as_view(
        template_name='main/assetlinks.json', content_type='application/json',
    )),
]
