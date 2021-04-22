from django.shortcuts import render




from django.views import View
from django.shortcuts import render
from django.http import JsonResponse
from main.models import (
    Subscription,
    SlpAddress
)
from operator import or_


class Test(View):
    
    def get(self, request, *args, **kwargs):
        address = kwargs['address']
        return render(request, 'main/test.html', {'address': address})

