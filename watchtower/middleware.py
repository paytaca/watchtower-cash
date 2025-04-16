class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Set Content-Security-Policy header
        response['Content-Security-Policy'] = "default-src 'self'; connect-src 'self' http://localhost:8000"
        return response
