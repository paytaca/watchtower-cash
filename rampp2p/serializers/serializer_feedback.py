from rest_framework import serializers
import rampp2p.models as models

class FeedbackCreateSerializer(serializers.ModelSerializer):
  from_peer = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
  to_peer = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
  order = serializers.PrimaryKeyRelatedField(queryset=models.Order.objects.all())

  class Meta:
    model = models.OrderFeedback
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
  order = serializers.PrimaryKeyRelatedField(queryset=models.Order.objects.all())

  class Meta:
    model = models.OrderFeedback
    fields = [
      "id",
      "from_peer",
      "to_peer",
      "order",
      "rating",
      "comment",
      "created_at"
    ]
  
  def get_from_peer(self, obj):
    return {
      'id': obj.from_peer.id,
      'name': obj.from_peer.name
    }
  
  def get_to_peer(self, obj):
     return {
      'id': obj.to_peer.id,
      'name': obj.to_peer.name
    }

class ArbiterFeedbackCreateSerializer(serializers.ModelSerializer):
    from_peer = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
    to_arbiter = serializers.PrimaryKeyRelatedField(queryset=models.Arbiter.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=models.Order.objects.all())

    class Meta:
        model = models.ArbiterFeedback
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
    order = serializers.PrimaryKeyRelatedField(queryset=models.Order.objects.all())

    class Meta:
        model = models.ArbiterFeedback
        fields = [
            "id",
            "peer",
            "arbiter",
            "order",
            "rating",
            "comment",
            "created_at"
        ]
    
    def get_peer(self, obj):
      return {
        'id': obj.from_peer.id,
        'name': obj.from_peer.name
      }
    
    def get_arbiter(self, obj):
      return {
        'id': obj.to_arbiter.id,
        'name': obj.to_arbiter.name
      }