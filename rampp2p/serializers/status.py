from rest_framework import serializers
from rampp2p.models import Status, Order

class StatusSerializer(serializers.ModelSerializer):
	order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
	seller_read_at = serializers.DateTimeField(required=False)
	buyer_read_at = serializers.DateTimeField(required=False)
	created_by = serializers.CharField(required=False, write_only=True)

	class Meta:
		model = Status
		fields = [
			'id',
			'status',
			'order',
			'created_at',
			'seller_read_at',
			'buyer_read_at',
			'created_by'
		]

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
		creator = obj.get_creator()
		if creator:
			creator = {
				'id': creator.id,
				'name': creator.name,
				'chat_identity_id': creator.chat_identity_id
			}
		return creator