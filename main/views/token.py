class SetupToken(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            data = list(subscriptions.values('id','token__name','token__tokenid', 'address__address'))
            return render(request, 'base/setuptoken.html', {"subscriptions": data})
        else:
            return render(request, 'base/login.html', query)

    def post(self, request):
        action = request.POST['action']
        status = 'failed'
        rowid =  request.POST['id']
        name = request.POST.get('name', None)
        sendto = request.POST.get('sendto', None)
        tokenid = request.POST.get('tokenid', None)
        if action == 'delete':
            qs = Subscription.objects.filter(id=rowid)
            if qs.exists():
                subscription = qs.first()
                subscription.delete()
                status = 'success'
        if action == 'add-edit':
            sendto_obj, created = SendTo.objects.get_or_create(address=sendto)
            token_obj, created = MyToken.objects.get_or_create(tokenid=tokenid)
            token_obj.name = name
            token_obj.save()
            if int(rowid) == 0:
                subscriber = Subscriber.objects.get(user=request.user)
                obj = Subscription()
                obj.address = sendto_obj
                obj.token = token_obj
                obj.save()
                subscriber.subscription.add(obj)
                status = 'success'
            else:
                qs = Subscription.objects.filter(id=rowid)
                if qs.exists():
                    qs.update(
                        address=sendto_obj,
                        token=token_obj 
                    )
                status = 'success'
        return JsonResponse({"status": status})
