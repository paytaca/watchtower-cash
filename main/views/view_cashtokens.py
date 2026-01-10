from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, mixins, decorators
# from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import OuterRef, Q, Exists
from django_filters import rest_framework as filters
# from rest_framework import status

from main.filters import CashNftFilter, TokensViewSetFilter
from main.models import (
    CashFungibleToken,
    CashNonFungibleToken,
    Transaction,
    # WalletHistory,
    # Token,
    # WalletNftToken
)
from main.serializers import (
    CashFungibleTokenSerializer,
    CashNonFungibleTokenSerializer,
    CashNonFungibleCategorySerializer,
    CashNonFungibleTokenGroupsSerializer,
    CashNonFungibleTokenItemsSerializer,
)

from smartbch.pagination import CustomLimitOffsetPagination


class CashFungibleTokensViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = CashFungibleToken.objects.all()
    serializer_class = CashFungibleTokenSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokensViewSetFilter,
    ]

    def get_serializer_context(self):
        """
        Add wallet_hash to serializer context so balance can be calculated.
        """
        context = super().get_serializer_context()
        wallet_hash = self.request.query_params.get('wallet_hash', None)
        if wallet_hash:
            context['wallet_hash'] = wallet_hash
        return context

    def list(self, request, *args, **kwargs):
        """
        Override list to order by favorites and favorite_order.
        Supports favorites_only query parameter to filter only favorited tokens.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        wallet_hash = request.query_params.get('wallet_hash', None)
        favorites_only = request.query_params.get('favorites_only', '').lower() == 'true'
        
        if favorites_only and not wallet_hash:
            # favorites_only requires wallet_hash
            from rest_framework import status
            return Response(
                {'error': 'wallet_hash is required when favorites_only=true'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if wallet_hash:
            # Get favorites data for ordering and filtering
            from main.models import AssetSetting

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
                favorites = None

            # Ensure we have a list (defensive check)
            if favorites is not None and not isinstance(favorites, list):
                favorites = None
            
            # Helper function to check if token is favorited
            def is_token_favorited(obj):
                token_id = obj.token_id  # Format: ct/{category}
                category = obj.category
                
                if favorites is None or len(favorites) == 0:
                    return False
                
                # Favorites is always a list: [{"id": "ct/...", "favorite": 1}, ...]
                for item in favorites:
                    if isinstance(item, dict):
                        item_id = item.get('id')
                        if item_id and (item_id == token_id or item_id == category):
                            # Check favorite value
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
            
            # Filter to only favorites if favorites_only is true
            if favorites_only:
                queryset = [obj for obj in queryset if is_token_favorited(obj)]
            else:
                queryset = list(queryset)
            
            # Create a helper function to get favorite status and order
            def get_favorite_info(obj):
                token_id = obj.token_id  # Format: ct/{category}
                category = obj.category
                is_favorite = False
                order = None
                
                if favorites:
                    # Favorites is always a list: [{"id": "ct/...", "favorite": 1}, ...]
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
                                    is_favorite = True
                                    order = favorite_order
                                    break
                                # Increment order for favorited items
                                favorite_order += 1
                
                return (not is_favorite, order if order is not None else float('inf'))
            
            # Sort: favorites first (is_favorite=False comes first when sorted ascending),
            # then by favorite_order ascending
            queryset.sort(key=get_favorite_info)
            
            # Paginate the sorted list
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        else:
            # No wallet_hash, use default pagination
            if favorites_only:
                from rest_framework import status
                return Response(
                    {'error': 'wallet_hash is required when favorites_only=true'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)


class CashNftsViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = CashNonFungibleToken.objects.all()
    serializer_class = CashNonFungibleTokenSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokensViewSetFilter,
        filters.DjangoFilterBackend,
    ]
    filterset_class = CashNftFilter

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name="wallet_hash", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
            ),
        ]
    )
    @decorators.action(detail=False, methods=["get"], filter_backends=[])
    def groups(self, request, *args, **kwargs):
        """
        Return a paginated list of unique NFT token categories.
        Each category is represented once (by its minting capability NFT if available, otherwise any NFT from the category).
        Categories with BCMR metadata (with_bcmr_metadata=True) are prioritized and appear first.
        """
        wallet_hash = request.query_params.get("wallet_hash", None)
        
        if wallet_hash:
            # Get all unique categories owned by this wallet
            owned_categories = CashNonFungibleToken.objects \
                .annotate_owner_wallet_hash() \
                .filter(owner_wallet_hash=wallet_hash) \
                .values_list("category", flat=True) \
                .distinct()
            
            # For each category, prefer minting NFT (especially if wallet owns it), 
            # but fallback to any NFT owned by wallet if minting doesn't exist
            nft_ids = []
            for category in owned_categories:
                # First try to find minting NFT owned by wallet
                minting_nft_owned = CashNonFungibleToken.objects.filter(
                    category=category,
                    capability=CashNonFungibleToken.Capability.MINTING
                ).annotate_owner_wallet_hash() \
                 .filter(owner_wallet_hash=wallet_hash) \
                 .order_by('-id').first()
                
                if minting_nft_owned:
                    nft_ids.append(minting_nft_owned.id)
                else:
                    # Try to find any minting NFT for this category (for representation)
                    minting_nft = CashNonFungibleToken.objects.filter(
                        category=category,
                        capability=CashNonFungibleToken.Capability.MINTING
                    ).order_by('-id').first()
                    
                    if minting_nft:
                        nft_ids.append(minting_nft.id)
                    else:
                        # Fallback to any NFT from this category owned by wallet (latest one)
                        any_nft = CashNonFungibleToken.objects.filter(
                            category=category
                        ).annotate_owner_wallet_hash() \
                         .filter(owner_wallet_hash=wallet_hash) \
                         .order_by('-id').first()
                        if any_nft:
                            nft_ids.append(any_nft.id)
            
            # If we found any NFTs, filter by their IDs, otherwise return empty queryset
            if nft_ids:
                queryset = CashNonFungibleToken.objects.filter(id__in=nft_ids)
            else:
                queryset = CashNonFungibleToken.objects.none()
        else:
            # No wallet filter - use existing filter_group logic (only minting NFTs)
            queryset = CashNonFungibleToken.objects.filter_group()

        # Order by metadata presence: categories with BCMR metadata (with_bcmr_metadata=True) first,
        # then categories without BCMR metadata (with_bcmr_metadata=False)
        queryset = queryset.order_by('-with_bcmr_metadata', '-id')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CashNonFungibleTokenGroupsSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = CashNonFungibleTokenGroupsSerializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name="wallet_hash", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
                description="Filter categories to only those owned by this wallet",
            ),
            openapi.Parameter(
                name="with_metadata", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
                description="Filter by metadata presence: 'true' for categories with metadata, 'false' for categories without metadata",
            ),
        ]
    )
    @decorators.action(detail=False, methods=["get"], filter_backends=[])
    def non_fungible(self, request, *args, **kwargs):
        """
        Return a paginated list of unique NFT token categories.
        Each item contains category and metadata (if available).
        """
        wallet_hash = request.query_params.get("wallet_hash", None)
        queryset = CashNonFungibleToken.objects.filter_group()
        
        # Filter by wallet_hash if provided
        if wallet_hash:
            owned_nfts_subq = CashNonFungibleToken.objects \
                .annotate_owner_wallet_hash() \
                .filter(owner_wallet_hash=wallet_hash) \
                .filter(category=OuterRef("category"))

            queryset = queryset \
                .filter(Exists(owned_nfts_subq))
        
        # Handle with_metadata filter parameter
        with_metadata = request.query_params.get("with_metadata", None)
        if with_metadata is not None:
            with_metadata = with_metadata.lower() == 'true'
            if with_metadata:
                # Only categories that have metadata (info is not null)
                queryset = queryset.filter(info__isnull=False)
            else:
                # Only categories that don't have metadata (info is null)
                queryset = queryset.filter(info__isnull=True)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CashNonFungibleCategorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = CashNonFungibleCategorySerializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name="category", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=True,
                description="Filter NFTs by category",
            ),
            openapi.Parameter(
                name="wallet_hash", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
                description="Filter NFTs to only those owned by this wallet",
            ),
            openapi.Parameter(
                name="has_metadata", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
                description="Filter by metadata presence: 'true' for NFTs with metadata, 'false' for NFTs without metadata",
            ),
        ]
    )
    @decorators.action(detail=False, methods=["get"], filter_backends=[TokensViewSetFilter, filters.DjangoFilterBackend])
    def items(self, request, *args, **kwargs):
        """
        Return a paginated list of NFT items for a given category.
        Can be filtered by wallet_hash and has_metadata.
        Returns the same format as /api/cashtokens/nft/ endpoint.
        """
        category = request.query_params.get("category", None)
        if not category:
            from rest_framework import status
            return Response(
                {'error': 'category parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Start with all NFTs filtered by category, ordered by latest first
        queryset = CashNonFungibleToken.objects.filter(category=category).order_by('-id')
        
        # Apply standard filters (wallet_hash, has_balance, etc.) using filter_backends
        queryset = self.filter_queryset(queryset)
        
        # Handle has_metadata filter parameter
        has_metadata = request.query_params.get("has_metadata", None)
        if has_metadata is not None:
            has_metadata = has_metadata.lower() == 'true'
            if has_metadata:
                # Only NFTs that have metadata (info is not null)
                queryset = queryset.filter(info__isnull=False)
            else:
                # Only NFTs that don't have metadata (info is null)
                queryset = queryset.filter(info__isnull=True)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CashNonFungibleTokenItemsSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = CashNonFungibleTokenItemsSerializer(queryset, many=True)
        return Response(serializer.data)
