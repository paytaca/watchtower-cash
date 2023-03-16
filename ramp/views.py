from django.shortcuts import render
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework import generics, status
from django.db.models import Q

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

# add deposit create
class RampWebhookView(APIView):

    def post(self, request):
        logger.info("Ramp Webhook")
        data = request.data
        # logger.info(data)
        
        ramp_data = data['payload']
        logger.info(ramp_data)

        type = data['type']
        logger.info(ramp_data['orderId'])

        shift_id = Shift.objects.filter(shift_id=ramp_data['orderId'])
        logger.info(shift_id)
        return Response({"success": True}, status=200)

class RampShiftView(APIView):

    def post(self, request):
        data = request.data
        data['date_shift_created'] = datetime.now()
        data['date_shift_completed'] = datetime.now()

        serializer = RampShiftSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(serializer.data)
        shift_id = serializer.data['shift_id']
        logger.info(shift_id)

        return Response({"success": True}, status=200)



class RampShiftHistoryView(generics.ListAPIView):
    serializer_class = RampShiftSerializer

    def get_queryset(self):
        wallet_hash = self.kwargs['wallet_hash']
        Model = self.serializer_class.Meta.model  

        list = Model.objects.filter(wallet_hash=wallet_hash)

        # logger.info(list)
        # logger.info(wallet_hash)
        
        return list