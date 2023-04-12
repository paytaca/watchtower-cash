from django.contrib import admin

# Register your models here.
from .models_base import *


admin.site.register(Ad)
admin.site.register(FiatCurrency)
admin.site.register(CryptoCurrency)
admin.site.register(Feedback)
admin.site.register(Order)
admin.site.register(Status)
admin.site.register(PaymentType)
admin.site.register(PaymentMethod)
admin.site.register(Peer)