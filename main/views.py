from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth import authenticate


from django.contrib.auth.models import User 

class Loginpage(View):

    def post(self, request):
        username = request.POST['username']
        password =  request.POST['password']
        post = User.objects.filter(username=username)
        if post:
            user = authenticate(request=request, username=username, password=password)
            if user is not None:
                request.user = user
                request.session['username'] = username
                return redirect('profile')
        return render(request, 'base/login.html', {})
        

class Profile(View):
    
    def get(self, request):
        if request.session.has_key('username'):
            posts = request.session['username']
            query = User.objects.filter(username=posts) 
            return render(request, 'base/profile.html', {"query":query})
        else:
            return render(request, 'base/login.html', {})

class Logout(View):

    def get(self, request):
        try:
            del request.session['username']
        except:
            pass
        return redirect('profile')
