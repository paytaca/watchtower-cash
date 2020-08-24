class SetAddressView(APIView):
    """
    Subscribers can set address using api view.
    * Requfires token authentication.
    * Permission should be authenticated.
    """
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    

    def post(self, request, format=None):
        tokenaddress = request.data.get('tokenAddress', None)
        destinationAddress = request.data.get('destinationAddress', None)
        tokenid = request.data.get('tokenid', None)
        tokenname = request.data.get('tokenname', None)
        reason = 'Invalid params.'
        status = 'failed'
        if tokenaddress and destinationAddress and tokenid and tokenname:
            subscriber_qs = Subscriber.objects.filter(user=request.user)
            reason = 'Not yet subscribed.'
            if subscriber_qs.exists():
                subscriber = subscriber_qs.first()
                sendto_obj, created = SendTo.objects.get_or_create(address=destinationAddress)
                if 'bitcoincash' in tokenaddress:
                    address_obj, created = BchAddress.objects.get_or_create(address=tokenaddress)
                    subscription_obj, created = Subscription.objects.get_or_create(bch=address_obj)
                    reason = 'BCH added.'
                else:
                    address_obj, created = SlpAddress.objects.get_or_create(address=tokenaddress)
                    subscription_obj, created = Subscription.objects.get_or_create(slp=address_obj)
                    reason = 'SLP added.'
                token_obj, created =  MyToken.objects.get_or_create(tokenid=tokenid)
                token_obj.name = tokenname.lower()
                subscription_obj.token = token_obj
                subscription_obj.save()
                subscription_obj.address.add(sendto_obj)
                subscriber.subscription.add(subscription_obj)
                status = 'success'
        return Response({'status': status, 'reason': reason})