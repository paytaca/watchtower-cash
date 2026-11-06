from rest_framework import serializers
from rampp2p.models import Status, Order, Arbiter


def serialize_creator(status: Status):
	'''Build the creator payload shared by the REST and WebSocket paths.

	`is_arbiter` is required because `Peer` and `Arbiter` have independent
	primary keys, so an id alone cannot disambiguate them.
	'''
	creator = status.get_creator()
	if creator:
		return {
			'id': creator.id,
			'name': creator.name,
			'chat_identity_id': creator.chat_identity_id,
			'is_arbiter': isinstance(creator, Arbiter)
		}
	if status.created_by == 'SYSTEM_AUTOMATED':
		return {'id': None, 'name': None, 'chat_identity_id': None, 'is_system': True}
	return None


class StatusSerializer(serializers.ModelSerializer):
	order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
	seller_read_at = serializers.DateTimeField(required=False)
	buyer_read_at = serializers.DateTimeField(required=False)
	created_by = serializers.CharField(required=False, write_only=True)
	creator = serializers.SerializerMethodField()

	class Meta:
		model = Status
		fields = [
			'id',
			'status',
			'order',
			'created_at',
			'creator',
			'seller_read_at',
			'buyer_read_at',
			'created_by'
		]

	def get_creator(self, obj: Status):
		return serialize_creator(obj)

class StatusReadSerializer(serializers.ModelSerializer):
	order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
	status = serializers.SerializerMethodField()
	creator = serializers.SerializerMethodField()

	class Meta:
		model = Status
		fields = [
			'id',
			'status',
			'order',
			'created_at',
			'creator',
			'seller_read_at',
			'buyer_read_at'
		]
	
	def get_status(self, obj: Status):
		return {
			'label': obj.get_status_display(),
			'value': obj.status
		}
	
	def get_creator(self, obj: Status):
		return serialize_creator(obj)