from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models.peer import Peer
from ..models.ad import Ad
from ..models.order import Order
from ..models.currency import FiatCurrency, CryptoCurrency
from ..models.payment import PaymentMethod, PaymentType

class FeedbackTest(APITestCase):
  def setUp(self):
    fiat = FiatCurrency.objects.create(name="PHP", abbrev="PHP")
    crypto = CryptoCurrency.objects.create(name="BCH", abbrev="BCH")
    self.seller = Peer.objects.create(nickname="FromPeer")
    self.buyer = Peer.objects.create(nickname="ToPeer")
    self.arbiter = Peer.objects.create(nickname="Arbiter")

    payment_type1 = PaymentType.objects.create(name="Gcash")
    payment_type2 = PaymentType.objects.create(name="Paypal")
    payment_method1 = PaymentMethod.objects.create(
      payment_type = payment_type1,
      owner = self.seller,
      account_name = "ACCOUNT NO. 1",
      account_number = "XXXXXXXXX",
    )
    payment_method2 = PaymentMethod.objects.create(
      payment_type = payment_type2,
      owner = self.seller,
      account_name = "ACCOUNT NO. 2",
      account_number = "XXXXXXXXX",
    )

    ad = Ad.objects.create(
      owner=self.seller,
      trade_type="SELL",
      price_type="FIXED",
      fiat_currency=fiat,
      crypto_currency=crypto,
      fixed_price=100,
      floating_price=0,
      trade_floor=100,
      trade_ceiling =1000,
      crypto_amount=10000,
      time_limit=60
    )
    ad.payment_methods.add(payment_method1)
    ad.payment_methods.add(payment_method2)
    ad.save()
    
    self.order = Order.objects.create(
      ad=ad,
      creator=self.buyer,
      crypto_currency=crypto,
      fiat_currency=fiat,
      fiat_amount=10000,
      locked_price=100,
      arbiter=self.arbiter
    )
    self.order.payment_methods.add(payment_method1)
    self.order.payment_methods.add(payment_method2)
    self.order.save()

  def test_arbiter_feedback_list_create(self):
    url = reverse('arbiter-feedback-list-create')
    data = {
      "from_peer": self.seller.id,
      "to_peer": self.arbiter.id,
      "order": self.order.id,
      "rating": 2,
      "comment": "Test comment"
    }
    response = self.client.get(url, data, format='json')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    # self.assertEqual(response.data, {'resul'})