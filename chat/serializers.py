from rest_framework import serializers
from chat.models import PgpInfo


class PgpInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgpInfo
        fields = (
            "user_id",
            "email",
            "public_key",
            "public_key_hash",
            "signature"
        )
