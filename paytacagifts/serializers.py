from rest_framework import serializers


class LimitOffsetPaginationInfoSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()


class GiftPayloadSerializer(serializers.Serializer):
    gift_code_hash = serializers.CharField()
    date_created = serializers.DateTimeField()
    amount = serializers.FloatField()
    campaign_id = serializers.CharField()
    date_claimed = serializers.DateTimeField()


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
    amount = serializers.FloatField()
    campaign = CampaignPayloadSerializer()


class ClaimGiftPayloadSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()


class RecoverGiftPayloadSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()


# #### responses
class CreateGiftResponseSerializer(serializers.Serializer):
    gift = serializers.CharField()


class ClaimGiftResponseSerializer(serializers.Serializer):
    share = serializers.CharField()
    claim_id = serializers.CharField()


class RecoverGiftResponseSerializer(serializers.Serializer):
    share = serializers.CharField()


class ListGiftsResponseSerializer(serializers.Serializer):
    gifts = GiftPayloadSerializer(many=True)
    pagination =  LimitOffsetPaginationInfoSerializer()


class ListCampaignsResponseSerializer(serializers.Serializer):
    campaigns = CampaignPayloadSerializer(many=True)
    pagination = LimitOffsetPaginationInfoSerializer()
