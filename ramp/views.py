from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from datetime import datetime

import json
import requests
import logging

from .models import (
    Shift
)
from .serializers import (
    RampShiftSerializer
)

logger = logging.getLogger(__name__)

# Create your views here.
class RampWebhookView(APIView):

    def post(self, request):
        logger.info("Ramp Webhook")
        ramp_data = request.data
        
        logger.info(ramp_data)
        return Response({"success": True, "data": ramp_data}, status=200)

class RampShiftView(APIView):

    def post(self, request):
        data = request.data
        data['date_shift_created'] = datetime.now()
        data['date_shift_completed'] = datetime.now()

        serializer = RampShiftSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(serializer.data)

        return Response({"success": True}, status=200)



# class RampShiftHistoryView():

#     def get(self, request):
