from django.views import View
from main.utils.queries.node import Node
from django.http import JsonResponse
from django.utils import timezone


NODE = Node()

class StatusView(View):

    def parse_boolean(self, value:str):
        if not isinstance(value, str): return None
        if value.lower() == 'true': return True
        if value.lower() == 'false': return False
        return None

    def get(self, request):
        response = {'status': 'up', 'health_checks': {}}
        response['timestamp'] = str(timezone.now())

        timestamp_only = self.parse_boolean(request.GET.get('timestamp_only'))
        if timestamp_only:
            del response['health_checks']
            return JsonResponse(response)

        # Test if node is down
        if NODE.BCH.get_latest_block():
            response['health_checks']['node'] = 'up'
        else:
            response['status'] = 'down'
            response['health_checks']['node'] = 'down'
        return JsonResponse(response)
 