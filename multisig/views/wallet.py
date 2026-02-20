import logging
from functools import wraps
from django.shortcuts import get_object_or_404
from django.db.models import Q

from multisig.models.auth import ServerIdentity
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError
from main.models import Transaction
from smartbch.pagination import CustomLimitOffsetPagination
import multisig.js_client as js_client
from multisig.auth.auth import PubKeySignatureMessageAuthentication, MultisigAuthentication
from multisig.models.wallet import MultisigWallet, Signer
from multisig.serializers.wallet import MultisigWalletSerializer, SignerSerializer, MultisigWalletUtxoSerializer
from multisig.auth.permission import IsCosigner, IsCosignerOfNewMultisigWallet
from rest_framework.generics import get_object_or_404 as drf_get_object_or_404

LOGGER = logging.getLogger(__name__)

from django.db import transaction

class MultisigWalletListCreateView(APIView):
    """
    Lists all multisig wallets or creates a new multisig wallet.
    """
    authentication_classes = [PubKeySignatureMessageAuthentication]

    def get(self, request):
        """
        List all multisig wallets that are not deleted.
        Optional: Add filter for include_deleted if needed.
        """
        queryset = MultisigWallet.objects.filter(deleted_at__isnull=True)
        include_deleted = request.query_params.get('include_deleted')
        if include_deleted in ('1', 'true', 'True'):
            queryset = MultisigWallet.objects.all()
        serializer = MultisigWalletSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        Create a new multisig wallet and associated signers atomically.
        Accepts `signers` as a field in the post data, creates Signer entries linked to the wallet.
        """
        data = request.data.copy()
        # signers_data = data.pop('signers', None)
        
        coordinator = ServerIdentity.objects.filter(public_key=request.headers.get('X-Auth-PubKey')).first()
        if not coordinator:
                return Response({'error': 'Coordinator needs server identity'}, status=status.HTTP_400_BAD_REQUEST)
        
        LOGGER.info(coordinator)
        serializer = MultisigWalletSerializer(
            data=data,
            context={"coordinator": coordinator}
        )

        serializer.is_valid(raise_exception=True)
        LOGGER.info(serializer.errors)
        wallet = serializer.save()

        status_code = status.HTTP_201_CREATED if getattr(serializer, "_created", True) else status.HTTP_200_OK

        return Response(
            MultisigWalletSerializer(wallet).data,
            status=status_code
        )

class MultisigWalletDetailView(APIView):
    """
    Retrieve a single MultisigWallet by its identifier (wallet_hash or wallet_descriptor_id).
    """

    def get(self, request, identifier):
        """
        Return details of a specific MultisigWallet matching the identifier.
        """
        # Optimize wallet lookup to allow searching by wallet_hash, wallet_descriptor_id, or id (as int).


        wallet = None

        filter_q = Q(wallet_hash=identifier) | Q(wallet_descriptor_id=identifier)

        if identifier.isdigit():
            filter_q = Q(id=identifier)

        wallet = (
            MultisigWallet.objects.filter(
                filter_q,
                deleted_at__isnull=True
            ).first()
        )
        
        if wallet is None:
            return Response({"error": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MultisigWalletSerializer(wallet)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SignerWalletListView(APIView):

    def get(self, request, public_key=None):
        """
        Returns all MultisigWallets associated with a signer,
        given a signer public key from the URL path (signers/<public_key>/wallets).
        """
        if not public_key:
            return Response({'error': 'Missing public_key parameter in URL'}, status=status.HTTP_400_BAD_REQUEST)
        wallets = MultisigWallet.objects.filter(signers__public_key=public_key, deleted_at__isnull=True).distinct()
        serializer = MultisigWalletSerializer(wallets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

