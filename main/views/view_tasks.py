import logging
from django.utils import timezone as tz
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema

from watchtower.celery import app as celery_app

from main import serializers

class TaskStatusView(APIView):
    @swagger_auto_schema(responses={200: serializers.TaskStatusSerializer})
    def get(request, *args, **kwargs):
        task_id = kwargs.get('task_id', '')
        task = celery_app.AsyncResult(task_id)
        data = {
            "status": task.status,
        }
        if task.ready():
            data["result"] = task.result
            data["date_done"] = task.date_done.__str__()

        # Might remove this part, takes around a second to perform (local & prod server)
        task_query = celery_app.control.inspect().query_task(task.id)
        for worker, queue in task_query.items():
            if task.id in queue:
                data["queue_info"] = queue[task.id]
                break

        return Response(data, status=status.HTTP_200_OK)
