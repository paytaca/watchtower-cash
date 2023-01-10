from rest_framework import serializers
from chat.models import PgpInfo


class PgpInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgpInfo
        fields = (
            "id",
            "address",
            "email",
            "public_key",
            "user_id"
        )
