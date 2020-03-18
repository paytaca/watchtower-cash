from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.contrib.auth import authenticate, login, logout
from main.models import (
    Subscriber,
    Token as MyToken,
    Transaction,
    Subscription,
    SendTo
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
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            ids = subscriptions.values('token__tokenid')
            tokens = MyToken.objects.filter(tokenid__in=ids).values_list('id', flat=True)
            transactions = Transaction.objects.filter(token__id__in=tokens).values(
                'id',
                'txid',
                'amount',
                'blockheight__number'
            )
            return render(request, 'base/home.html', {"transactions": transactions})
        else:
            return render(request, 'base/login.html', query)

class Account(View):
    
    # def get(self, request):
    #     query = {}
    #     if request.user.is_authenticated:
    #         query = User.objects.filter(username=request.user.username) 
    #         return render(request, 'base/account.html', {"query":query})
    #     else:
    #         return render(request, 'base/login.html', query)

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
        

class Token(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            data = list(subscriptions.values('id','token__tokenid', 'address__address'))
            return render(request, 'base/tokens.html', {"subscriptions": data})
        else:
            return render(request, 'base/login.html', query)

    def post(self, request):
        action = request.POST['action']
        status = 'failed'
        rowid =  request.POST['id']
        sendto = request.POST['sendto']
        tokenid = request.POST['tokenid']
        if action == 'delete':
            qs = Subscription.objects.filter(id=rowid)
            if qs.exists():
                subscription = qs.first()
                subscription.delete()
                status = 'success'
        if action == 'add-edit':
            sendto_obj, created = SendTo.objects.get_or_create(address=sendto)
            token_obj, created = MyToken.objects.get_or_create(tokenid=tokenid)
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