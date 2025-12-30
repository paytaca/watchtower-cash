from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from paytacagifts.serializers import (ListGiftsResponseSerializer, CreateGiftPayloadSerializer, ClaimGiftPayloadSerializer,
                                    ClaimGiftResponseSerializer,RecoverGiftResponseSerializer, RecoverGiftPayloadSerializer,
                                    CreateGiftResponseSerializer, GetGiftResponseSerializer)
from paytacagifts.models import Gift, Wallet, Campaign, Claim

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from main.utils.subscription import new_subscription
from main.utils.queries.node import Node
from main.models import Transaction, TransactionMetaAttribute
from django.db.models import Sum, F, Q
from datetime import datetime
import logging
import hashlib

NODE = Node()
LOGGER = logging.getLogger(__name__)

class GiftViewSet(viewsets.GenericViewSet):
    lookup_field = "wallet_hash"

    @action(detail=True, methods=['get'])
    @swagger_auto_schema(
        operation_description="Fetches a list of Gifts filtered by wallet hash with pagination.",
        responses={
            status.HTTP_200_OK: ListGiftsResponseSerializer
        },
        manual_parameters=[
            openapi.Parameter('offset', openapi.IN_QUERY, description="Offset for pagination.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Limit for pagination.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('type', openapi.IN_QUERY, description="Filter by gift type: 'unclaimed' or 'claimed'.", type=openapi.TYPE_STRING, enum=['unclaimed', 'claimed']),
            openapi.Parameter('campaign', openapi.IN_QUERY, description="Filter by campaign ID.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('created_by_wallet', openapi.IN_QUERY, description="Filter by creation: true (only created by wallet), false (only claimed by wallet), null (both). Only applies when type=claimed.", type=openapi.TYPE_BOOLEAN),
        ]
    )
    def list_gifts(self, request, wallet_hash=None):
        count = None
        type_filter = None
        campaign_filter = None
        created_by_wallet = None
        offset = 0
        limit = 0
        query_args = request.query_params
        wallet_hash = self.kwargs[self.lookup_field]
        
        if query_args.get("offset"):
            offset = int(query_args.get("offset"))

        if query_args.get("limit"):
            limit = int(query_args.get("limit"))

        if query_args.get("type"):
            type_filter = query_args.get("type", None)
            if type_filter:
                type_filter = str(type_filter).lower().strip()

        if query_args.get("campaign"):
            campaign_filter = query_args.get("campaign", None)

        # Parse created_by_wallet parameter
        if query_args.get("created_by_wallet") is not None:
            created_by_wallet_str = str(query_args.get("created_by_wallet")).lower().strip()
            if created_by_wallet_str == "true":
                created_by_wallet = True
            elif created_by_wallet_str == "false":
                created_by_wallet = False
            # else remains None

        # Base queryset: always filter by date_funded
        queryset = Gift.objects.filter(date_funded__isnull=False)
        
        # Apply type filter
        if type_filter == "unclaimed":
            # Unclaimed gifts: date_claimed is null (if date_claimed is None, it can't be recovered)
            # Only show gifts created by the wallet (unchanged behavior)
            queryset = queryset.filter(
                wallet__wallet_hash=wallet_hash,
                date_claimed__isnull=True
            )
        elif type_filter == "claimed":
            # Claimed gifts: date_claimed is not null (includes both regular claims and recovered gifts)
            queryset = queryset.filter(date_claimed__isnull=False)
            
            # Apply wallet filter based on created_by_wallet parameter
            if created_by_wallet is True:
                # Only gifts created by wallet
                queryset = queryset.filter(wallet__wallet_hash=wallet_hash)
            elif created_by_wallet is False:
                # Only gifts claimed by wallet (but not created by it)
                queryset = queryset.filter(
                    claims__wallet__wallet_hash=wallet_hash
                ).exclude(wallet__wallet_hash=wallet_hash)
            else:
                # Default (null): gifts created by wallet OR claimed by wallet
                queryset = queryset.filter(
                    Q(wallet__wallet_hash=wallet_hash) |
                    Q(claims__wallet__wallet_hash=wallet_hash)
                )
            # Apply distinct() to avoid duplicates when a gift matches both conditions
            queryset = queryset.distinct()
        else:
            # No type filter specified, default to gifts created by wallet
            queryset = queryset.filter(wallet__wallet_hash=wallet_hash)

        if isinstance(campaign_filter, str):
            queryset = queryset.filter(campaign__id=campaign_filter)

        count = queryset.count()
        queryset = queryset.order_by('-date_created')
        
        # Calculate has_next before slicing
        has_next = False
        if limit:
            has_next = (offset + limit) < count
        elif offset:
            has_next = offset < count
        
        # Apply pagination
        if offset:
            queryset = queryset[offset:]
        if limit:
            queryset = queryset[:limit]

        gifts = []
        # Convert queryset to list to ensure all fields are loaded
        gift_list = list(queryset)
        for gift in gift_list:
            campaign = gift.campaign
            campaign_id = None
            campaign_name = None
            if campaign:
                campaign_id = str(campaign.id)
                campaign_name = str(campaign.name)
            recovered = False
            claim = gift.claims.first()
            if claim:
                if gift.wallet_id == claim.wallet_id and gift.date_claimed is not None:
                    recovered = True
            # Get encrypted_gift_code, handling both None and empty string
            encrypted_gift_code = gift.encrypted_gift_code if gift.encrypted_gift_code else ''
            gift_data = {
                "gift_code_hash": str(gift.gift_code_hash),
                "date_created": str(gift.date_created),
                "amount": gift.amount,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "date_claimed": str(gift.date_claimed),
                "recovered": recovered,
                "encrypted_gift_code": encrypted_gift_code
            }
            # Add created_by field for claimed gifts (SHA-256 hash of creator's wallet_hash)
            if gift.date_claimed is not None:
                gift_data["created_by"] = hashlib.sha256(gift.wallet.wallet_hash.encode()).hexdigest()
            gifts.append(gift_data)

        data = {
            "gifts": gifts,
            "pagination": {
                "count": count,
                "offset": offset,
                "limit": limit,
                "has_next": has_next
            }
        }
        return Response(data)
        
    @swagger_auto_schema(
        request_body=CreateGiftPayloadSerializer,
        responses={status.HTTP_200_OK: CreateGiftResponseSerializer},
        manual_parameters=[
            openapi.Parameter('wallet_hash', openapi.IN_PATH, description="Wallet Hash", type=openapi.TYPE_STRING, required=True),
        ]
    )
    def create(self, request, *args, **kwargs):
        data = request.data
        wallet_hash = kwargs.get("wallet_hash", "")
        if not wallet_hash: raise Exception('Wallet Hash Required')
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        if "campaign" in data:
            if "limit_per_wallet" in data["campaign"]:
                limit = data["campaign"]["limit_per_wallet"]
                name = data["campaign"]["name"]
                campaign = Campaign.objects.create(name=name, wallet=wallet, limit_per_wallet=limit)
            elif "id" in data["campaign"]:
                campaign = Campaign.objects.get(id=data["campaign"]["id"])
        else:
            campaign = None
        # subscribe address
        new_subscription(address=data["address"])
        # create gift record
        gift, created = Gift.objects.get_or_create(
            gift_code_hash=data["gift_code_hash"],
            wallet=wallet
        )
        if created:
            gift.address=data["address"]
            gift.amount=data["amount"]
            gift.encrypted_share = data.get('encrypted_share') or ''
            gift.encrypted_gift_code = data.get('encrypted_gift_code') or ''
            gift.share=data["share"]
            gift.campaign=campaign
            gift.save()
        return Response({"gift": str(gift)})

    @action(detail=True, methods=['post'])
    @swagger_auto_schema(
        operation_id="gift_claim",
        operation_description="Claim a Gift record.",
        request_body=ClaimGiftPayloadSerializer,
        responses={
            status.HTTP_200_OK: ClaimGiftResponseSerializer
        }
    )
    def claim(self, request, gift_code_hash):
        wallet_hash = request.data["wallet_hash"]
        transaction_hex = request.data.get("transaction_hex", "").strip()
        
        # If transaction_hex is provided, broadcast it synchronously before proceeding
        # Only proceed with claim creation if broadcast succeeds
        broadcast_success = True
        broadcast_error = None
        txid = None
        if transaction_hex:
            # Check if node is available
            if not NODE.BCH.get_latest_block():
                return Response({
                    "success": False,
                    "message": "Blockchain node is not available",
                }, status=503)
            
            # Test mempool acceptance
            try:
                test_accept = NODE.BCH.test_mempool_accept(transaction_hex)
                if not test_accept.get('allowed', False):
                    reject_reason = test_accept.get('reject-reason', 'Unknown error')
                    return Response({
                        "success": False,
                        "message": f"Transaction rejected by mempool: {reject_reason}",
                    }, status=400)
                # Extract txid for later use in metadata
                txid = test_accept.get('txid')
            except Exception as exc:
                error_msg = str(exc)
                LOGGER.exception(f"Error testing mempool acceptance: {exc}")
                return Response({
                    "success": False,
                    "message": f"Error testing mempool acceptance: {error_msg}",
                }, status=400)
            
            # Check if transaction already exists
            if not Transaction.objects.filter(txid=txid).exists():
                # Broadcast synchronously
                try:
                    broadcast_result = NODE.BCH.broadcast_transaction(transaction_hex)
                    # broadcast_transaction returns txid on success, or raises exception on failure
                    if not broadcast_result:
                        return Response({
                            "success": False,
                            "message": "Transaction broadcast failed: No txid returned",
                        }, status=400)
                    broadcast_success = True
                except Exception as exc:
                    error_msg = str(exc)
                    # Some nodes return "already have transaction" which is actually success
                    if 'already have transaction' not in error_msg.lower():
                        LOGGER.exception(f"Error broadcasting transaction: {exc}")
                        return Response({
                            "success": False,
                            "message": f"Transaction broadcast failed: {error_msg}",
                        }, status=400)
                    broadcast_success = True
            else:
                # Transaction already exists, consider broadcast successful
                broadcast_success = True
        
        # Only proceed with claim creation if broadcast succeeded (or no transaction_hex was provided)
        if transaction_hex and not broadcast_success:
            return Response({
                "success": False,
                "message": broadcast_error or "Transaction broadcast failed",
            }, status=400)
        
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        gift_qs = Gift.objects.filter(gift_code_hash=gift_code_hash)
        if not gift_qs.exists():
            raise Exception("Gift does not exist!")
        gift = gift_qs.first()
        claim = Claim.objects.filter(gift=gift.id, wallet=wallet).first()
        
        if claim:
            # Create or update transaction metadata if txid is available
            if txid:
                TransactionMetaAttribute.objects.update_or_create(
                    txid=txid,
                    wallet_hash=wallet_hash,
                    system_generated=True,
                    key="gift_claim",
                    defaults=dict(
                        value="Gift"
                    )
                )
            
            # Build response - old clients get original format, new clients get enhanced format
            response_data = {
                "share": gift.share,
                "encrypted_share": gift.encrypted_share,
                "claim_id": str(claim.id)
            }
            if transaction_hex:
                # New clients get success and encrypted_gift_code
                response_data["success"] = True
                response_data["encrypted_gift_code"] = gift.encrypted_gift_code or ''
            return Response(response_data)

        if gift.campaign:
            claims = gift.campaign.claims.filter(wallet__wallet_hash=wallet_hash, succeeded=True)
            claims_sum = claims.aggregate(Sum('amount'))['amount__sum'] or 0
            if claims_sum < gift.campaign.limit_per_wallet:
                claim = Claim.objects.create(
                    wallet=wallet,
                    amount=gift.amount,
                    gift=gift,
                    campaign=gift.campaign
                )
            else:
                # Error response - only include success/message for new clients
                if transaction_hex:
                    return Response({
                        "success": False,
                        "message": "You have exceeded the limit of gifts to claim for this campaign",
                    }, status=400)
                else:
                    return Response({
                        "message": "You have exceeded the limit of gifts to claim for this campaign",
                    }, status=400)
        else:
            claim = Claim.objects.create(
                wallet=wallet,
                amount=gift.amount,
                gift=gift
            )

        if claim:
            # Create transaction metadata for gift claim
            if txid:
                TransactionMetaAttribute.objects.update_or_create(
                    txid=txid,
                    wallet_hash=wallet_hash,
                    system_generated=True,
                    key="gift_claim",
                    defaults=dict(
                        value="Gift"
                    )
                )
            # Build response - old clients get original format, new clients get enhanced format
            response_data = {
                "share": gift.share,
                "encrypted_share": gift.encrypted_share,
                "claim_id": str(claim.id)
            }
            if transaction_hex:
                # New clients get success and encrypted_gift_code
                response_data["success"] = True
                response_data["encrypted_gift_code"] = gift.encrypted_gift_code or ''
            return Response(response_data)
        else:
            # Error response - only include success/message for new clients
            if transaction_hex:
                return Response({
                    "success": False,
                    "message": "This gift has been claimed",
                }, status=400)
            else:
                return Response({
                    "message": "This gift has been claimed",
                }, status=400)


    @swagger_auto_schema(
        operation_description="Get share and encrypted_share for a gift by gift code hash.",
        responses={
            status.HTTP_200_OK: GetGiftResponseSerializer,
            status.HTTP_404_NOT_FOUND: openapi.Response(description="Gift not found")
        },
        manual_parameters=[
            openapi.Parameter('gift_code_hash', openapi.IN_PATH, description="Gift code hash", type=openapi.TYPE_STRING, required=True),
        ]
    )
    def retrieve_by_hash(self, request, gift_code_hash=None):
        """Retrieve share and encrypted_share for a gift given its gift_code_hash."""
        gift_qs = Gift.objects.filter(gift_code_hash=gift_code_hash)
        if not gift_qs.exists():
            return Response({
                "error": "Gift does not exist"
            }, status=status.HTTP_404_NOT_FOUND)
        
        gift = gift_qs.first()
        return Response({
            "share": gift.share,
            "encrypted_share": gift.encrypted_share
        })

    @action(detail=True, methods=['post'])
    @swagger_auto_schema(
        operation_description="Recover funds from a gift.",
        request_body=RecoverGiftPayloadSerializer,
        responses={
            status.HTTP_200_OK: RecoverGiftResponseSerializer
        }
    )
    def recover(self, request, gift_code_hash):
        wallet_hash = request.data["wallet_hash"]
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        gift_qs = Gift.objects.filter(wallet=wallet, gift_code_hash=gift_code_hash)
        if not gift_qs.exists():
            raise Exception("Gift does not exist!")
        gift = gift_qs.first()
        if gift:
            claim_check = Claim.objects.filter(gift=gift)
            if claim_check.exists():
                raise Exception("This gift has been claimed.")
            else:
                Claim.objects.create(
                    wallet=wallet,
                    amount=gift.amount,
                    gift=gift
                )
                return Response({
                    "share": gift.share,
                    "encrypted_share": gift.encrypted_share,
                    "encrypted_gift_code": gift.encrypted_gift_code or ''
                })
        else:
            raise Exception("This gift does not exist.")
