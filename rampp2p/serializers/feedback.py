from rest_framework import serializers
from ..models.feedback import Feedback
from ..models.peer import Peer
from ..models.order import Order

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