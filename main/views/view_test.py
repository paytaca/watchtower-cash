from django.shortcuts import render
from django.views import View
from django.shortcuts import render
from django.views.generic.base import TemplateView


class TestSocket(View):
    template_name = 'main/test.html'

    def get(self, request, *args, **kwargs):
        address = kwargs['address']
        tokenid = ''
        if not address.startswith('bitcoincash'):
            tokenid = kwargs.get('tokenid', '')
        return render(request, self.template_name, {'address': address, 'tokenid': tokenid})
