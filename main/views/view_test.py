from django.shortcuts import render
from django.views import View
from django.shortcuts import render


class Test(View):
    
    def get(self, request, *args, **kwargs):
        address = kwargs['address']
        return render(request, 'main/test.html', {'address': address})

