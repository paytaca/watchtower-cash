from rest_framework.viewsets import ViewSet
from django.shortcuts import render
from django.http import JsonResponse
from main.models import (
    Subscriber,
    Subscription,
    SlpAddress
)
from operator import or_

class SetupSLPAddress(ViewSet):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            data = []
            for subscription in subscriptions:
                if subscription.slp:
                    data.append({'slp__id': subscription.slp.id, 'slp__address': subscription.slp.address})
            return render(request, 'base/setupaddress.html', {
                "subscriptions": data,
            })
        else:
            return render(request, 'base/login.html', query)

    def post(self, request):
        action = request.POST['action']
        rowid =  request.POST['id']
        status = 'failed'
        slpaddress = request.POST.get('slpaddress', None)
        if action == 'delete':
            qs = SlpAddress.objects.filter(id=rowid)
            if qs.exists():
                slpaddress = qs.first()
                slpaddress.delete()
                status = 'success'
        if action == 'add-edit':
            address_obj, created = SlpAddress.objects.get_or_create(address=slpaddress)
            if int(rowid) == 0:
                subscriber = Subscriber.objects.get(user=request.user)
                obj = Subscription()
                obj.slp = address_obj
                obj.save()
                subscriber.subscription.add(obj)
                status = 'success'
            else:
                qs = Subscription.objects.filter(id=rowid)
                if qs.exists():
                    qs.update(
                        address=address_obj,
                    )
                status = 'success'
        return JsonResponse({"status": status})
