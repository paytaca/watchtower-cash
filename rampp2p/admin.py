from django.contrib import admin

# Register your models here.
from rampp2p.models import *


admin.site.register(Ad)
admin.site.register(AdSnapshot)
admin.site.register(FiatCurrency)
admin.site.register(CryptoCurrency)
admin.site.register(Feedback)
admin.site.register(Order)
admin.site.register(Status)
admin.site.register(PaymentType)
admin.site.register(PaymentMethod)
admin.site.register(Peer)
admin.site.register(MarketRate)
admin.site.register(Arbiter)
admin.site.register(Contract)
admin.site.register(Appeal)
admin.site.register(ContractMember)