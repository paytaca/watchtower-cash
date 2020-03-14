from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth import authenticate


from django.contrib.auth.models import User 

class Loginpage(View):

    def post(self, request):
        username = request.POST['username']
        password =  request.POST['password']
        user = User.objects.filter(username=username)
        if user.exists():
            user = authenticate(request=request, username=username, password=password)
            if user is not None:
                request.user = user
                request.session['username'] = username
                return redirect('home')
        return render(request, 'base/login.html', {})
        

class Home(View):
    
    def get(self, request):
        query = {}
        if request.session.has_key('username'):
            users = request.session['username']
            query = User.objects.filter(username=users) 
            return render(request, 'base/home.html', {"query":query})
        else:
            return render(request, 'base/login.html', query)

class Account(View):
    
    def get(self, request):
        query = {}
        if request.session.has_key('username'):
            users = request.session['username']
            query = User.objects.filter(username=users) 
            return render(request, 'base/account.html', {"query":query})
        else:
            return render(request, 'base/login.html', query)


class Settings(View):
    
    def get(self, request):
        query = {}
        if request.session.has_key('username'):
            users = request.session['username']
            query = User.objects.filter(username=users) 
            return render(request, 'base/settings.html', {"query":query})
        else:
            return render(request, 'base/login.html', query)

class Logout(View):

    def get(self, request):
        try:
            del request.session['username']
        except:
            pass
        return redirect('home')
