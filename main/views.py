from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.contrib.auth import authenticate, login, logout
from main.models import Subscriber
from django.contrib.auth.models import User 
from django.urls import reverse
import json



class Loginpage(View):

    def post(self, request):
        username = request.POST['username']
        password =  request.POST['password']
        user = User.objects.filter(username=username)
        if user.exists():
            user = authenticate(request=request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('home')
        return render(request, 'base/login.html', {})
        

class Home(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            query = User.objects.filter(username=request.user.username) 
            return render(request, 'base/home.html', {"query":query})
        else:
            return render(request, 'base/login.html', query)

class Account(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            query = User.objects.filter(username=request.user.username) 
            return render(request, 'base/account.html', {"query":query})
        else:
            return render(request, 'base/login.html', query)

class Token(View):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            query = User.objects.filter(username=request.user.username) 
            return render(request, 'base/token.html', {"query":query})
        else:
            return render(request, 'base/login.html', query)

    def post(self, request):
        user_qs = User.objects.filter(username=users)
        status = 'failed'
        if user_qs.exists():
            user = user_qs.first()
            subscription_qs = Subscriber.objects.filter(user=user)
            if subscription_qs.exists():
                subscriber = subscription_qs.first()
                # Get all token changes and update the model

                # token = models.ManyToManyField(Token, related_name='subscriber')
                # data = JSONField(default=None, null=True)
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