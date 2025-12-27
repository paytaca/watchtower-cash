from rest_framework import serializers


class LimitOffsetPaginationInfoSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    has_next = serializers.BooleanField()


class GiftPayloadSerializer(serializers.Serializer):
    gift_code_hash = serializers.CharField()
    date_created = serializers.DateTimeField()
    amount = serializers.FloatField()
    campaign_id = serializers.CharField()
    date_claimed = serializers.DateTimeField()
    recovered = serializers.BooleanField(default=False)
    encrypted_gift_code = serializers.CharField(required=False, allow_blank=True)


class CampaignPayloadSerializer(serializers.Serializer):
    id = serializers.CharField()
    date_created = serializers.DateTimeField()
    name = serializers.CharField()
    limit_per_wallet = serializers.FloatField()
    gifts = serializers.IntegerField()
    claims = serializers.IntegerField()    


class CreateGiftPayloadSerializer(serializers.Serializer):
    gift_code_hash = serializers.CharField()
    address = serializers.CharField()
    share = serializers.CharField()
    encrypted_share = serializers.CharField(required=False, allow_blank=True)
    encrypted_gift_code = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.FloatField()
    campaign = CampaignPayloadSerializer(required=False, allow_null=True)


class ClaimGiftPayloadSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()
    transaction_hex = serializers.CharField(required=False, allow_blank=True, help_text='Optional transaction hex ready for broadcast. If provided, will be broadcast synchronously before marking the gift as claimed.')


class RecoverGiftPayloadSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()


# #### responses
class CreateGiftResponseSerializer(serializers.Serializer):
    gift = serializers.CharField()


class ClaimGiftResponseSerializer(serializers.Serializer):
    share = serializers.CharField(required=False)
    encrypted_share = serializers.CharField(required=False)
    encrypted_gift_code = serializers.CharField(required=False, allow_blank=True)
    claim_id = serializers.CharField(required=False)
    success = serializers.BooleanField(required=False, help_text='Only included when transaction_hex is provided (new clients)')
    message = serializers.CharField(required=False, allow_blank=True, help_text='Error message when success is False (only for new clients with transaction_hex)')


class RecoverGiftResponseSerializer(serializers.Serializer):
    share = serializers.CharField()
    encrypted_share = serializers.CharField()
    encrypted_gift_code = serializers.CharField(required=False, allow_blank=True)


class ListGiftsResponseSerializer(serializers.Serializer):
    gifts = GiftPayloadSerializer(many=True)
    pagination =  LimitOffsetPaginationInfoSerializer()


class ListCampaignsResponseSerializer(serializers.Serializer):
    campaigns = CampaignPayloadSerializer(many=True)
    pagination = LimitOffsetPaginationInfoSerializer()
