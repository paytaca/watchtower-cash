from django.shortcuts import render
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework import generics, status
from django.db.models import Q

from django.core.paginator import Paginator
from datetime import datetime

import json
import requests
import logging

from .tasks import (
    update_shift_status
)

from .models import (
    Shift
)
from .serializers import (
    RampShiftSerializer
)

logger = logging.getLogger(__name__)

def _save_shift(data):
    logger.info('Saving Data')
    logger.info(data)
    payload = data['payload']
    # info = {
    #     # "wallet_hash": ,
    #     # "bch_address": ,
    #     # "ramp_type",
    #     "shift_id": payload['id'],
    #     # "quote_id": payload[''],
    #     # "date_shift_created",
    #     # "date_shift_completed",
    #     "shift_info",
    #     "shift_status": 
    # }


# add deposit create
class RampWebhookView(APIView):

    def post(self, request):
        logger.info("Ramp Webhook")
        # update_shift_status()
        data = request.data
        # logger.info(data)
        
        ramp_data = data['payload']
        # logger.info(ramp_data)

        type = data['type']
        logger.info(type)

        # shift_id = Shift.objects.filter(shift_id=ramp_data['orderId'])
        # logger.info(shift_id)

        # if shift_id:
        #     logger.info('saved')
        # else:
        #     logger.info('not saved')

        # if not shift_id:
        #     if data['type'] == 'order:create':
        #         _save_shift(data)


        return Response({"success": True}, status=200)
        



class RampShiftView(APIView):

    def post(self, request):
        data = request.data
        
        date_text = data['date_shift_created']

        date = datetime.strptime(date_text, "%Y-%m-%dT%H:%M:%S.%fZ")
        logger.info(date.time())
        logger.info(date.date())
        data['date_shift_created'] = date


        serializer = RampShiftSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        shift_id = serializer.data['shift_id']        

        return Response({"success": True}, status=200)



class RampShiftHistoryView(APIView):
    serializer_class = RampShiftSerializer

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs['wallet_hash']
        page = request.query_params.get('page', 1)
        Model = self.serializer_class.Meta.model 

        # logger.info('page:')
        # logger.info(page)

        qs = Model.objects.filter(wallet_hash=wallet_hash).order_by('-date_shift_created')

        list = qs.values(                
            "ramp_type",
            "shift_id",
            "quote_id",
            "date_shift_created",
            "date_shift_completed",
            "shift_info",
            "shift_status"
        )
        # logger.info(list)

        pages = Paginator(list, 10)
        page_obj = pages.page(int(page))
        data = {
            'history': page_obj.object_list,
            'page': page,
            'num_pages': pages.num_pages,
            'has_next': page_obj.has_next()
        }

        return Response(data, status=200) 