from rest_framework import serializers


class TaskStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    date_done = serializers.DateTimeField(required=False)
    result = serializers.JSONField(required=False)
    queue_info = serializers.JSONField(required=False)
