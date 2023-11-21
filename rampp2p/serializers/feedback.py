from rest_framework import serializers
from rampp2p.models import (
    Arbiter,
    Peer,
    Order,
    Feedback,
    ArbiterFeedback
)

class FeedbackCreateSerializer(serializers.ModelSerializer):
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

class FeedbackSerializer(serializers.ModelSerializer):
  from_peer = serializers.SerializerMethodField()
  to_peer = serializers.SerializerMethodField()
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
      "created_at"
    ]
  
  def get_from_peer(self, instance: Feedback):
    return {
      'id':       instance.from_peer.id,
      'name': instance.from_peer.name
    }
  
  def get_to_peer(self, instance: Feedback):
     return {
      'id':       instance.to_peer.id,
      'name': instance.to_peer.name
    }

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
    peer = serializers.SerializerMethodField()
    arbiter = serializers.SerializerMethodField()
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())

    class Meta:
        model = ArbiterFeedback
        fields = [
            "id",
            "peer",
            "arbiter",
            "order",
            "rating",
            "comment",
            "created_at"
        ]
    
    def get_peer(self, instance: ArbiterFeedback):
      return {
        'id': instance.from_peer.id,
        'name': instance.from_peer.name
      }
    
    def get_arbiter(self, instance: ArbiterFeedback):
      return {
        'id': instance.to_arbiter.id,
        'name': instance.to_arbiter.name
      }