from django.shortcuts import render
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework import generics, status
from django.db.models import Q
from django.conf import settings 

from django.core.paginator import Paginator
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
        data = request.data
        type = data['type']
        logger.info("Ramp Webhook: " + type.upper())
        logger.info(data)
        
        # ramp_data = data['payload']
    
        return Response({"success": True}, status=200)
        


class RampShiftView(APIView):

    def post(self, request):
        data = request.data

        info = {
            'depositCoin': data['deposit']['coin'],
            'depositNetwork': data['deposit']['network'],
            'settleCoin': data['settle']['coin'],
            'settleNetwork': data['settle']['network'],
            'depositAmount': data['amount']
        }
        params = json.dumps(info)
        headers = {
            'Content-Type': 'application/json',
            'x-sideshift-secret': settings.SIDESHIFT_SECRET_KEY,
            'x-user-ip': data['ramp_settings']['user_ip']
        }
        # Get Quote    
        quote_url = "https://sideshift.ai/api/v2/quotes"
        quote = requests.post(
            quote_url,
            data = params,
            headers = headers
        )

        if quote.status_code == 200 or quote.status_code == 201:
            # Fixed Shift 
            shift_url = "https://sideshift.ai/api/v2/shifts/fixed"
            info = {
                'settleAddress': data['settle_address'],
                'quoteId': quote.json()['id'],
                'refundAddress': data['refund_address']
            }
            params = json.dumps(info)

            fixed_shift = requests.post(
                shift_url,
                data = params,
                headers = headers
            )            

            if fixed_shift.status_code == 200 or fixed_shift.status_code == 201:
                # Save To DB
                shift_data = fixed_shift.json()
                date_text = shift_data['createdAt']
                date = datetime.strptime(date_text, "%Y-%m-%dT%H:%M:%S.%fZ")

                # stage data
                info = {
                    'wallet_hash': data['ramp_settings']['wallet_hash'],
                    'bch_address': data['ramp_settings']['bch_address'],
                    'ramp_type': data['ramp_settings']['type'],
                    'shift_id': shift_data['id'],
                    'quote_id': shift_data['quoteId'],
                    'date_shift_created': date,
                    'shift_status': shift_data['status'],
                    'shift_info': {
                        'deposit': {
                            'address': shift_data['depositAddress'],
                            'amount': shift_data['depositAmount'],
                            'coin': shift_data['depositCoin'],
                            'network': shift_data['depositNetwork'],
                            'icon': data['deposit']['icon']
                        },
                        'settle': {
                            'address': shift_data['settleAddress'],
                            'amount': shift_data['settleAmount'],
                            'coin': shift_data['settleCoin'],
                            'network': shift_data['settleNetwork'],
                            'icon': data['settle']['icon']
                        },
                        'shift_expiration': shift_data['expiresAt']
                    }
                }

                serializer = RampShiftSerializer(data=info)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                
                return Response(fixed_shift.json(), status=200)  

        return Response({"failed": True}, status=500)
    
class RampShiftExpireView(APIView):
    serializer_class = RampShiftSerializer

    def post(self, request):
        data = request.data
        # wallet_hash = data['wallet_hash']
        shift_id = data['shift_id']
        Model = self.serializer_class.Meta.model

        shift = Model.objects.filter(shift_id=shift_id)
        if shift:
            shift = shift.first()
            shift.shift_status = 'expired'
            shift.save()

            return Response({"success": True}, status=200)
        else:
            return Response({"success": False}, status=200)

    
class RampShiftHistoryView(APIView):
    serializer_class = RampShiftSerializer

    def get(self, request, *args, **kwargs):
        
        wallet_hash = kwargs['wallet_hash']
        page = request.query_params.get('page', 1)
        address = request.query_params.get('address', '')
        Model = self.serializer_class.Meta.model 
        data = {}

        qs = Model.objects.filter(wallet_hash=wallet_hash, bch_address=address).order_by('-date_shift_created')

        if qs:
            list = qs.values(                
                "ramp_type",
                "shift_id",
                "quote_id",
                "date_shift_created",
                "date_shift_completed",
                "shift_info",
                "shift_status"
            )

            pages = Paginator(list, 10)
            page_obj = pages.page(int(page))
            data = {
                'history': page_obj.object_list,
                'page': page,
                'num_pages': pages.num_pages,
                'has_next': page_obj.has_next()
            }
        else:
            logger.info('no such address')
        return Response(data, status=200)
