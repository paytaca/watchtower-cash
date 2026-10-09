from rest_framework import serializers

from main.models import WalletLookupKey


class WalletLookupKeyCreateSerializer(serializers.ModelSerializer):
    """
    Mint a lookup key for the authenticated wallet.

    `wallet` is deliberately absent from `fields`. It is not an optional input:
    the view always binds `request.user`'s wallet via serializer.save(), so the
    field can never legitimately be supplied.

    Declaring it as `required=False` would not work. That means "may be absent",
    not "ignore if present" -- as a PrimaryKeyRelatedField (Wallet's PK is the
    auto integer id) it would still *validate* a supplied value and reject the
    wallet_hash string callers actually send, with "Incorrect type. Expected pk
    value, received str". Marking it read_only has the same problem in the
    generated schema, where the field keeps showing up in the request body.

    Omitting it entirely is the honest expression: the field cannot be set here.
    """

    class Meta:
        model = WalletLookupKey
        fields = ['label']


class WalletLookupKeyCreatedSerializer(serializers.ModelSerializer):
    """
    The create response. This is the ONLY place the raw key appears -- it is
    never stored, so it cannot be retrieved again.

    `lookup_key` is declared here for documentation and schema purposes only.
    It is not a model field, so serializing an instance yields no `lookup_key`
    key at all and this serializer alone cannot render the raw value. The view
    injects it into the response dict after `.data`; see the mint handler.
    """
    lookup_key = serializers.CharField(read_only=True)

    class Meta:
        model = WalletLookupKey
        fields = ['id', 'lookup_key', 'label', 'date_created']


class WalletLookupKeyAssetBalanceSerializer(serializers.Serializer):
    asset_id = serializers.CharField(read_only=True)
    balance = serializers.FloatField(read_only=True)
    decimals = serializers.IntegerField(read_only=True, required=False)
    found = serializers.BooleanField(read_only=True, required=False)
    name = serializers.CharField(read_only=True, required=False)
    symbol = serializers.CharField(read_only=True, required=False)


class WalletLookupKeyBalanceSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(read_only=True)
    bch = serializers.DictField(read_only=True)
    assets = WalletLookupKeyAssetBalanceSerializer(many=True, read_only=True)
