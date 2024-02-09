from django.views import View
from main.utils.queries.node import Node
from django.http import JsonResponse


NODE = Node()

class StatusView(View):

    def get(self, request):
        response = {'status': 'up', 'health_checks': {}}
        # Test if node is down
        if NODE.BCH.get_latest_block():
            response['health_checks']['node'] = 'up'
        else:
            response['status'] = 'down'
            response['health_checks']['node'] = 'down'
        return JsonResponse(response)
 