from rest_framework import serializers

from django.conf import settings
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from main.models import (
    CashNonFungibleToken,
    CashFungibleToken,
    CashTokenInfo,
    Transaction,
    Wallet,
    AssetSetting,
)

from datetime import timedelta


class CashTokenInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashTokenInfo
        fields = [
            'name',
            'description',
            'symbol',
            'decimals',
            'image_url',
            'nft_details',
        ]


class CashFungibleTokenSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True, source='token_id')
    name = serializers.SerializerMethodField()
    symbol = serializers.SerializerMethodField()
    decimals = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    favorite = serializers.SerializerMethodField()
    favorite_order = serializers.SerializerMethodField()
    
    class Meta:
        model = CashFungibleToken
        fields = [
            'id',
            'name',
            'symbol',
            'decimals',
            'image_url',
            'balance',
            'favorite',
            'favorite_order',
        ]

    def get_name(self, obj):
        if obj.info:
            return obj.info.name
        return settings.DEFAULT_TOKEN_DETAILS['fungible']['name']

    def get_symbol(self, obj):
        if obj.info:
            return obj.info.symbol
        return settings.DEFAULT_TOKEN_DETAILS['fungible']['symbol']

    def get_decimals(self, obj):
        if obj.info:
            return obj.info.decimals
        return 0

    def get_image_url(self, obj):
        if obj.info:
            return obj.info.image_url
        return None

    def truncate(self, num, decimals):
        """
        Truncate instead of rounding off
        Rounding off sometimes results to a value greater than the actual balance
        """
        # Preformat first if it it's in scientific notation form
        if 'e-' in str(num):
            num, power = str(num).split('e-')
            power = int(power)
            num = num.replace('.', '')
            left_pad = (power - 1) * '0'
            sp = '0.' + left_pad + num
        else:
            sp = str(num)
        # Proceed to truncate
        sp = sp.split('.')
        if len(sp) == 2:
            return float('.'.join([sp[0], sp[1][:decimals]]))
        else:
            return num

    def get_balance(self, obj):
        """
        Get balance for this token by calculating it from the database.
        Returns None if wallet_hash is not provided in context.
        """
        wallet_hash = self.context.get('wallet_hash')
        if not wallet_hash:
            return None

        # Calculate balance from database
        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        except Wallet.DoesNotExist:
            return 0

        query = Q(wallet=wallet) & Q(cashtoken_ft=obj) & Q(spent=False)
        qs_balance = Transaction.objects.filter(query).aggregate(
            amount_sum=Coalesce(Sum('amount'), 0)
        )

        balance = qs_balance['amount_sum'] or 0
        decimals = self.get_decimals(obj)

        if balance > 0:
            balance = self.truncate(balance, decimals)

        return balance

    def _get_favorites_data(self):
        """
        Helper method to get favorites data from database.
        Returns favorites list or None if not found.
        Favorites are always stored as a list: [{"id": "ct/...", "favorite": 1}, ...]
        """
        wallet_hash = self.context.get('wallet_hash')
        if not wallet_hash:
            return None

        # Query database directly
        try:
            asset_setting = AssetSetting.objects.only('favorites').get(wallet_hash=wallet_hash)
            favorites = asset_setting.favorites

            # Ensure favorites is a list (should be after migration)
            if not isinstance(favorites, list):
                favorites = []

            # Normalize empty list to None for consistency
            if len(favorites) == 0:
                favorites = None

        except AssetSetting.DoesNotExist:
            return None

        # Ensure we have a list (defensive check)
        if favorites is not None and not isinstance(favorites, list):
            return None

        return favorites

    def get_favorite(self, obj):
        """
        Check if this token is in the user's favorites list.
        Returns False if wallet_hash is not provided in context or token is not favorited.
        Favorites structure: [{"id": "ct/...", "favorite": 1}, ...]
        """
        favorites = self._get_favorites_data()
        if favorites is None or len(favorites) == 0:
            return False

        token_id = obj.token_id  # Format: ct/{category}
        category = obj.category

        # Favorites is always a list: [{"id": "ct/...", "favorite": 1}, ...]
        for item in favorites:
            if isinstance(item, dict):
                item_id = item.get('id')
                if item_id and (item_id == token_id or item_id == category):
                    # favorite: 1 means favorited, 0 means not favorited
                    favorite_value = item.get('favorite', 0)
                    # Ensure it's an int (should be after migration/validation)
                    if not isinstance(favorite_value, int):
                        try:
                            favorite_value = int(favorite_value)
                        except (ValueError, TypeError):
                            favorite_value = 0
                    return favorite_value == 1
        
        # Token not found in favorites list
        return False

    def get_favorite_order(self, obj):
        """
        Get the favorite_order value for this token.
        Returns None if wallet_hash is not provided or token is not favorited.
        The order is determined by the position in the favorites array among favorited items.
        Favorites structure: [{"id": "ct/...", "favorite": 1}, ...]
        """
        favorites = self._get_favorites_data()
        if favorites is None or len(favorites) == 0:
            return None

        token_id = obj.token_id  # Format: ct/{category}
        category = obj.category

        # Favorites is always a list: [{"id": "ct/...", "favorite": 1}, ...]
        # favorite_order is the index among items where favorite: 1
        favorite_order = 0
        for item in favorites:
            if isinstance(item, dict):
                item_id = item.get('id')
                item_favorite = item.get('favorite', 0)
                
                # Ensure it's an int (should be after migration/validation)
                if not isinstance(item_favorite, int):
                    try:
                        item_favorite = int(item_favorite)
                    except (ValueError, TypeError):
                        item_favorite = 0
                
                # Only count items that are favorited (favorite: 1)
                if item_favorite == 1:
                    # Check if this is the token we're looking for
                    if item_id and (item_id == token_id or item_id == category):
                        return favorite_order
                    # Increment order for favorited items
                    favorite_order += 1
        
        # Token not found or not favorited
        return None
            

class CashNonFungibleTokenSerializer(serializers.ModelSerializer):
    info = CashTokenInfoSerializer()
    
    class Meta:
        model = CashNonFungibleToken
        fields = [
            'id',
            'category',
            'commitment',
            'capability',
            'current_txid',
            'current_index',
            'info',
        ]
