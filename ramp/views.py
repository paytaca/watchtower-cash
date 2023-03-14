from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response

import json
import requests
import logging

logger = logging.getLogger(__name__)

# Create your views here.
class RampWebhookView(APIView):

    def post(self, request):
        logger.info("Ramp Webhook")
        ramp_data = request.data
        
        logger.info(ramp_data)
        return Response({"success": True, "data": ramp_data}, status=200)
