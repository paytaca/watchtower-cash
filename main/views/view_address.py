from rest_framework.viewsets import ViewSet
from django.shortcuts import render
from django.http import JsonResponse
from main.models import (
    Subscription,
    Address
)
from operator import or_






class SetupSLPAddress(ViewSet):
    
    def get(self, request):
        # query = {}
        # if request.user.is_authenticated:
        #     subscriber = Subscriber.objects.get(user=request.user)
        #     subscriptions = subscriber.subscription.all()
        #     data = []
        #     for subscription in subscriptions:
        #         if subscription.slp:
        #             data.append({'slp__id': subscription.slp.id, 'slp__address': subscription.slp.address})
        #     return render(request, 'base/setupaddress.html', {
        #         "subscriptions": data,
        #     })
        # else:
        return render(request, 'base/login.html', query)

    def post(self, request):
        # action = request.POST['action']
        # rowid =  request.POST['id']
        # status = 'failed'
        # slpaddress = request.POST.get('slpaddress', None)
        # if action == 'delete':
        #     qs = SlpAddress.objects.filter(id=rowid)
        #     if qs.exists():
        #         slpaddress = qs.first()
        #         slpaddress.delete()
        #         status = 'success'
        # if action == 'add-edit':
        #     address_obj, created = SlpAddress.objects.get_or_create(address=slpaddress)
        #     if int(rowid) == 0:
        #         subscriber = Subscriber.objects.get(user=request.user)
        #         obj = Subscription()
        #         obj.slp = address_obj
        #         obj.save()
        #         subscriber.subscription.add(obj)
        #         status = 'success'
        #     else:
        #         qs = Subscription.objects.filter(id=rowid)
        #         if qs.exists():
        #             qs.update(
        #                 address=address_obj,
        #             )
        status = 'success'
        return JsonResponse({"status": status})



# SLPAddress Model ViewSet

from main.models import Address
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from main.serializers import AddressSerializer

class AddressViewSet(viewsets.ModelViewSet):
    """
    A viewset that provides the standard actions
    """
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    http_method_names = ['get', 'post', 'head']