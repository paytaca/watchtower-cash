from django.shortcuts import render
from rest_framework.views import APIView

import json

# Create your views here.
class RampWebhookView(APIView):

    def post(self, request, *args, **kwargs):
        ramp_data = json.loads(request.body)

        print('Ramp Webhook')
        print(ramp_data)