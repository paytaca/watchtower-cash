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