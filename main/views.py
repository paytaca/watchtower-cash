from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.contrib.auth import authenticate, login, logout
from main.models import (
    Subscriber,
    Token as MyToken,
    Transaction,
    Subscription,
    SendTo,
    SlpAddress
)
from django.contrib.auth.models import User 
from django.urls import reverse
import json



class Loginpage(View):

    def post(self, request):
        username = request.POST['username']
        password =  request.POST['password']
        user = User.objects.filter(username=username)
        if user.exists():
            subscriber = Subscriber.objects.get(user=user.first())
            if subscriber.confirmed:
                user = authenticate(request=request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    return redirect('home')
        return render(request, 'base/login.html', {})
        

class Home(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            token = request.GET.get('token', 'all')
            slpaddress = request.GET.get('slp', 'all')
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            new = True
            if not subscriptions.count():
                new = False
            if token != 'all':
                subscriptions = subscriptions.filter(token__tokenid=token)
            if slpaddress != 'all':
                slpaddress = int(slpaddress)
                subscriptions = subscriptions.filter(slp__id=slpaddress)
            
            transactions = Transaction.objects.all()
            if token != 'all':
                ids = subscriptions.values('token__tokenid')
                tokens = MyToken.objects.filter(tokenid__in=ids).values_list('id', flat=True)
                transactions = transactions.filter(
                    token__id__in=tokens
                )
            if slpaddress != 'all':
                trids = SlpAddress.objects.filter(id=slpaddress).values_list('transactions__id', flat=True)
                transactions = transactions.filter(
                    id__in=trids
                )
            transactions.values(
                'id',
                'txid',
                'amount',
                'blockheight__number'
            )
            subs = subscriber.subscription.all()
            slpaddresses = list(subs.values('slp__id', 'slp__address'))
            tokens = list(subs.values('token__tokenid', 'token__name'))
            slpaddresses.insert(0, {
                'slp__id': 'all',
                'slp__address': 'All SLP Addresses'
            })
            tokens.insert(0, {
                'token__tokenid': 'all',
                'token__name': 'All Tokens' 
            })
            return render(request, 'base/home.html', {
                "new": new,
                "transactions": transactions,
                "querytoken": token,
                "queryslpaddress": slpaddress,
                "slpaddresses": slpaddresses,
                "tokens": tokens
            })
        else:
            return render(request, 'base/login.html', query)

class Account(View):
    

    def post(self, request):
        action = request.POST['action']
        status = 'failed'
        if action == 'register':
            firstname = request.POST['firstname']
            lastname = request.POST['lastname']
            email = request.POST['email']
            password = request.POST['password']
            username = request.POST['username']
            # Create User
            user = User()
            user.username = username
            user.first_name = firstname
            user.last_name = lastname
            user.email = email
            user.save()
            user.set_password(password)
            user.save()
            # Create Subscriber
            subscriber = Subscriber()
            subscriber.user = user
            subscriber.save()
            status = 'success'
            return redirect('home')
        if action == 'update':
            return redirect('account')
        

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


class SetupSLPAddress(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            data = []
            for subscription in subscriptions:
                if subscription.slp:
                    data.append({'slp__id': subscription.slp.id, 'slp__address': subscription.slp.address})
            return render(request, 'base/setupaddress.html', {
                "subscriptions": data,
            })
        else:
            return render(request, 'base/login.html', query)

    def post(self, request):
        action = request.POST['action']
        rowid =  request.POST['id']
        status = 'failed'
        slpaddress = request.POST.get('slpaddress', None)
        if action == 'delete':
            qs = SlpAddress.objects.filter(id=rowid)
            if qs.exists():
                slpaddress = qs.first()
                slpaddress.delete()
                status = 'success'
        if action == 'add-edit':
            address_obj, created = SlpAddress.objects.get_or_create(address=slpaddress)
            if int(rowid) == 0:
                subscriber = Subscriber.objects.get(user=request.user)
                obj = Subscription()
                obj.slp = address_obj
                obj.save()
                subscriber.subscription.add(obj)
                status = 'success'
            else:
                qs = Subscription.objects.filter(id=rowid)
                if qs.exists():
                    qs.update(
                        address=address_obj,
                    )
                status = 'success'
        return JsonResponse({"status": status})


class Logout(View):

    def get(self, request):
        from django.contrib.auth import logout
        logout(request)
        return redirect('home')


class SignUp(View):

    def post(self, request):
        data = json.loads(request.body)
        username = data.get('username', '')
        fname = data.get('firstname', '')
        lname = data.get('lastname', '')
        email = data.get('email', '')
        password = data.get('password', '')
        status = 'failed'
        if username and fname and lname and email and password:
            # process the subscription here
            # Subscriber
            status = 'success'
        return JsonResponse({"status": status}) 