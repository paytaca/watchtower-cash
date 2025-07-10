import logging
from functools import wraps
from django.shortcuts import get_object_or_404
from django.db.models import Q
from multisig.auth.auth import MultisigAuthentication
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from main.models import Transaction
from smartbch.pagination import CustomLimitOffsetPagination
import multisig.js_client as js_client
from ..models.wallet import MultisigWallet
from ..serializers.wallet import MultisigWalletSerializer, MultisigWalletUtxoSerializer
from ..auth.permission import IsCosigner, IsCosignerOfNewMultisigWallet

LOGGER = logging.getLogger(__name__)

class MultisigWalletListCreateView(APIView):
    
    authentication_classes = [MultisigAuthentication]
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsCosigner()]
        elif self.request.method == 'POST':
            return [IsCosignerOfNewMultisigWallet()]
        else:
            return super().get_permissions()

    def get(self, request):
        
        queryset = MultisigWallet.objects.filter(deleted_at__isnull=True)

        include_deleted = request.query_params.get('include_deleted')

        if include_deleted == '1' or include_deleted == 'true':
            queryset = MultisigWallet.objects.all()
        
        xpub = request.query_params.get('xpub')

        if xpub:
            queryset = queryset.filter(signers__xpub=xpub).distinct()

        serializer = MultisigWalletSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MultisigWalletSerializer(data=request.data)
        
        if serializer.is_valid():
            wallet = serializer.save()
            return Response(MultisigWalletSerializer(wallet).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class MultisigWalletDetailView(APIView):
   
    authentication_classes = [MultisigAuthentication]
    permission_classes = [IsCosigner]

    def get(self, request, wallet_identifier):
        try:
            if wallet_identifier.isdigit():
                wallet = MultisigWallet.objects.get(id=wallet_identifier)
            else:
                wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier)
        except MultisigWallet.DoesNotExist:
            raise NotFound(detail="Wallet not found.")
        serializer = MultisigWalletSerializer(wallet)
        return Response(serializer.data)
    
    def delete(self, request, wallet_identifier):
        
        try:
            if wallet_identifier.isdigit():
                identifier_name = 'id'
                wallet = MultisigWallet.objects.get(id=wallet_identifier)
            else:
                identifier_name = 'locking_bytecode'
                wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier)

            if not wallet.deleted_at:
                wallet.soft_delete()
            else:
                wallet.delete()

            return Response({"message": f"Wallet with {identifier_name}={wallet_identifier} deleted."}, status=status.HTTP_200_OK)

        except MultisigWallet.DoesNotExist:
            raise NotFound(detail="Wallet with {identifier_name}={identifier} Not Found.")
        

class RenameMultisigWalletView(APIView):

    authentication_classes = [MultisigAuthentication]
    permission_classes = [IsCosigner]

    def patch(self, request, pk):
        try:
            wallet = MultisigWallet.objects.get(pk=pk)
        except MultisigWallet.DoesNotExist:
            return Response({"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND)

        new_name = request.data.get("name")
        if not new_name:
            return Response({"detail": "Name field is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Django 3.0.14 requires full reassignment to track JSONField changes
        template = wallet.template.copy()
        template["name"] = new_name
        wallet.template = template
        wallet.save()

        return Response({"id": wallet.id, "name": new_name}, status=status.HTTP_200_OK)

class MultisigWalletUtxosView(APIView):
    serializer_class = MultisigWalletUtxoSerializer
    pagination_class = CustomLimitOffsetPagination
    def get(self, request, address):
        queryset = Transaction.objects.filter(spent=False, address__address=address)
        
        only_tokens = request.query_params.get('only_tokens')
        if only_tokens == 'true':     # return only token utxos
            queryset = queryset.filter(Q(amount__gt=0) | Q(cashtoken_ft__category__isnull=False) | Q(cashtoken_nft__category__isnull=False))
        
        token_type = request.query_params.get('token_type')
        if token_type == 'ft':     # ft (may have capability also)
            queryset = queryset.filter(Q(amount__gt=0) & Q(cashtoken_ft__category__isnull=False))

        if token_type == 'nft':    # nft (may have ft also)
            queryset = queryset.filter(Q(cashtoken_nft__category__isnull=False) & Q(cashtoken_nft__capability__isnull=False))

        if token_type == 'hybrid': # strictly hybrid
            queryset = queryset.filter(Q(amount__gt=0) & Q(cashtoken_ft__category__isnull=False) & Q(cashtoken_nft__category__isnull=False) & Q(cashtoken_nft__capability__isnull=False))

        if token_type == 'nft' or token_type == 'hybrid':
            capability = self.request.query_params.get('capability')
            commitment = self.request.query_params.get('commitment')
            commitment_ne = self.request.query_params.get('commitment_ne')
            if capability:
                queryset = queryset.filter(cashtoken_nft__capability=capability)
            if commitment:
                queryset = queryset.filter(cashtoken_nft__commitment=commitment)
            if commitment_ne:
                queryset = queryset.filter(~Q(cashtoken_nft__commitment=commitment_ne))
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(~Q(cashtoken_nft__category=category))
        
        paginate = request.query_params.get('paginate', False)
        if paginate:
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(queryset, request)
            if page is not None:
                serializer = self.serializer_class(page, many=True)
                return paginator.get_paginated_response(serializer.data)
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)
