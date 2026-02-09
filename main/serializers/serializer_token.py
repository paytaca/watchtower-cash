from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import serializers, exceptions

from main.models import AssetSetting, Token, Transaction, Wallet

class TokenSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True, source="info_id")
    image_url = serializers.CharField(read_only=True)
    symbol = serializers.CharField(read_only=True, source="token_ticker")

    success = serializers.BooleanField(read_only=True)

    class Meta:
        model = Token
        fields = [
            'id',
            'name',
            'symbol',
            'decimals',
            'token_type',
            'image_url',
            'success',
        ]


class SlpFungibleTokenSerializer(serializers.ModelSerializer):
    """
    Serializer for fungible SLP tokens, mirroring CashTokens fungible response shape:
    id, name, symbol, decimals, image_url, balance, favorite, favorite_order
    """

    id = serializers.CharField(read_only=True, source="info_id")
    name = serializers.CharField(read_only=True)
    symbol = serializers.CharField(read_only=True, source="token_ticker")
    decimals = serializers.IntegerField(read_only=True)
    image_url = serializers.CharField(read_only=True)
    balance = serializers.SerializerMethodField()
    favorite = serializers.SerializerMethodField()
    favorite_order = serializers.SerializerMethodField()

    class Meta:
        model = Token
        fields = [
            "id",
            "name",
            "symbol",
            "decimals",
            "image_url",
            "balance",
            "favorite",
            "favorite_order",
        ]

    def truncate(self, num, decimals):
        """
        Truncate instead of rounding off.
        Rounding off sometimes results to a value greater than the actual balance.
        """
        # Preformat first if it it's in scientific notation form
        if "e-" in str(num):
            num, power = str(num).split("e-")
            power = int(power)
            num = num.replace(".", "")
            left_pad = (power - 1) * "0"
            sp = "0." + left_pad + num
        else:
            sp = str(num)
        # Proceed to truncate
        sp = sp.split(".")
        if len(sp) == 2:
            return float(".".join([sp[0], sp[1][:decimals]]))
        else:
            return num

    def get_balance(self, obj):
        """
        Get balance for this token by calculating it from the database.
        Returns None if wallet_hash is not provided in context.
        """
        wallet_hash = self.context.get("wallet_hash")
        if not wallet_hash:
            return None

        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        except Wallet.DoesNotExist:
            return 0

        query = Q(wallet=wallet) & Q(token=obj) & Q(spent=False)
        qs_balance = Transaction.objects.filter(query).aggregate(
            amount_sum=Coalesce(Sum("amount"), 0)
        )

        balance = qs_balance["amount_sum"] or 0
        decimals = obj.decimals or 0

        if balance > 0:
            balance = self.truncate(balance, decimals)

        return balance

    def _get_favorites_data(self):
        """
        Helper method to get favorites data from database.
        Returns favorites list or None if not found.
        Favorites are always stored as a list: [{"id": "...", "favorite": 1}, ...]
        """
        wallet_hash = self.context.get("wallet_hash")
        if not wallet_hash:
            return None

        try:
            asset_setting = AssetSetting.objects.only("favorites").get(wallet_hash=wallet_hash)
            favorites = asset_setting.favorites

            if not isinstance(favorites, list):
                favorites = []
            if len(favorites) == 0:
                favorites = None

        except AssetSetting.DoesNotExist:
            return None

        if favorites is not None and not isinstance(favorites, list):
            return None

        return favorites

    def _matches_favorite_id(self, favorite_id: str, obj: Token) -> bool:
        """
        Favorites IDs are expected to be `slp/<tokenid>`, but accept raw tokenid for compatibility.
        """
        if not favorite_id:
            return False
        return favorite_id == obj.info_id or favorite_id == obj.tokenid

    def get_favorite(self, obj):
        """
        Check if this token is in the user's favorites list.
        Returns False if wallet_hash is not provided in context or token is not favorited.
        """
        favorites = self._get_favorites_data()
        if favorites is None or len(favorites) == 0:
            return False

        for item in favorites:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not item_id:
                continue
            if not self._matches_favorite_id(str(item_id).strip(), obj):
                continue

            favorite_value = item.get("favorite", 0)
            if not isinstance(favorite_value, int):
                try:
                    favorite_value = int(favorite_value)
                except (ValueError, TypeError):
                    favorite_value = 0
            return favorite_value == 1

        return False

    def get_favorite_order(self, obj):
        """
        Get the favorite_order value for this token.
        Returns None if wallet_hash is not provided or token is not favorited.
        The order is determined by the position in the favorites array among favorited items.
        """
        favorites = self._get_favorites_data()
        if favorites is None or len(favorites) == 0:
            return None

        favorite_order = 0
        for item in favorites:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not item_id:
                continue

            item_favorite = item.get("favorite", 0)
            if not isinstance(item_favorite, int):
                try:
                    item_favorite = int(item_favorite)
                except (ValueError, TypeError):
                    item_favorite = 0

            if item_favorite == 1:
                if self._matches_favorite_id(str(item_id).strip(), obj):
                    return favorite_order
                favorite_order += 1

        return None


class WalletTokenSerializer(serializers.Serializer):
    token_id = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    symbol = serializers.CharField(required=False, allow_blank=True)
    type = serializers.IntegerField(required=False)
    nft_token_group = serializers.CharField(required=False)
    original_image_url = serializers.CharField(required=False, allow_blank=True)
    medium_image_url = serializers.CharField(required=False, allow_blank=True)
    thumbnail_image_url = serializers.CharField(required=False, allow_blank=True)
    txid = serializers.CharField(required=False, allow_blank=True)
    date_acquired = serializers.DateTimeField(required=False)
    count = serializers.IntegerField(required=False)
