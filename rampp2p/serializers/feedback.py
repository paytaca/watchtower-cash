from rest_framework import serializers
from rampp2p.models import (
    Arbiter,
    Peer,
    Order,
    Feedback,
    ArbiterFeedback
)

class FeedbackSerializer(serializers.ModelSerializer):
  from_peer = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  to_peer = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())

  class Meta:
    model = Feedback
    fields = [
      "id",
      "from_peer",
      "to_peer",
      "order",
      "rating",
      "comment",
    ]
    read_only_fields = [
      "from_peer",
      "to_peer",
      "order"
    ]

class ArbiterFeedbackCreateSerializer(serializers.ModelSerializer):
    from_peer = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    to_arbiter = serializers.PrimaryKeyRelatedField(queryset=Arbiter.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())

    class Meta:
        model = ArbiterFeedback
        fields = [
            "from_peer",
            "to_arbiter",
            "order",
            "rating",
            "comment",
            "created_at"
        ]

class ArbiterFeedbackSerializer(serializers.ModelSerializer):
    peer_name = serializers.SerializerMethodField()
    arbiter_name = serializers.SerializerMethodField()
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())

    class Meta:
        model = ArbiterFeedback
        fields = [
            "id",
            "peer_name",
            "arbiter_name",
            "order",
            "rating",
            "comment",
            "created_at"
        ]
    
    def get_peer_name(self, instance: ArbiterFeedback):
       return instance.from_peer.nickname
    
    def get_arbiter_name(self, instance: ArbiterFeedback):
       return instance.to_arbiter.name