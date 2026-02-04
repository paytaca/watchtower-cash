import logging
from functools import wraps
from django.shortcuts import get_object_or_404
from django.db.models import Q

from multisig.models.coordinator import ServerIdentity
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
    # permission_classes = [IsCosignerOfNewMultisigWallet]

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
        signers_data = data.pop('signers', None)
        with transaction.atomic():
            coordinator = ServerIdentity.objects.filter(public_key=request.headers.get('X-Auth-PubKey')).first()
            if not coordinator:
                return Response({'error': 'Coordinator needs server identity'}, status=status.HTTP_400_BAD_REQUEST)
            data['coordinator'] = coordinator.id
            wallet = MultisigWallet.objects.filter(coordinator=coordinator, wallet_descriptor_id=data['walletDescriptorId']).first()
            if wallet:
                serializer = MultisigWalletSerializer(wallet)
                return Response(serializer.data, status=status.HTTP_200_OK)

            serializer = MultisigWalletSerializer(data=data)
            if serializer.is_valid():
                wallet = serializer.save()
                created_signers = []
                if signers_data and isinstance(signers_data, list):
                    for signer_dict in signers_data:
                        signer_serializer = SignerSerializer(data={**signer_dict, 'wallet': wallet.id})
                        if signer_serializer.is_valid():
                            signer = signer_serializer.save()
                            created_signers.append(signer)
                        else:
                            raise ValidationError({
                                'error': 'Invalid signer data',
                                'signer_errors': signer_serializer.errors
                            })
                wallet_serialized = MultisigWalletSerializer(wallet).data
                wallet_serialized['signers'] = SignerSerializer(wallet.signers.all(), many=True).data
                return Response(wallet_serialized, status=status.HTTP_201_CREATED)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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


# class MultisigWalletDetailView(APIView):

#     authentication_classes = [PubKeySignatureMessageAuthentication]
#     permission_classes = [IsCosigner]

#     def get(self, request, wallet_identifier):
#         # Retrieve a wallet either by numeric ID or locking_bytecode
#         try:
#             if wallet_identifier.isdigit():
#                 wallet = MultisigWallet.objects.get(id=wallet_identifier, deleted_at__isnull=True)
#             else:
#                 wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier, deleted_at__isnull=True)
#         except MultisigWallet.DoesNotExist:
#             raise NotFound("MultisigWallet not found")

#         serializer = MultisigWalletSerializer(wallet)
#         return Response(serializer.data)

#     def delete(self, request, wallet_identifier):
#         try:
#             if wallet_identifier.isdigit():
#                 wallet = MultisigWallet.objects.get(id=wallet_identifier, deleted_at__isnull=True)
#             else:
#                 wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier, deleted_at__isnull=True)
#         except MultisigWallet.DoesNotExist:
#             raise NotFound("MultisigWallet not found")

#         wallet.soft_delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)

#     def put(self, request, wallet_identifier):
#         try:
#             if wallet_identifier.isdigit():
#                 wallet = MultisigWallet.objects.get(id=wallet_identifier, deleted_at__isnull=True)
#             else:
#                 wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier, deleted_at__isnull=True)
#         except MultisigWallet.DoesNotExist:
#             raise NotFound("MultisigWallet not found")

#         serializer = MultisigWalletSerializer(wallet, data=request.data, partial=True)
#         if serializer.is_valid():
#             wallet = serializer.save()
#             return Response(MultisigWalletSerializer(wallet).data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# class SignerListCreateView(APIView):

#     authentication_classes = [PubKeySignatureMessageAuthentication, MultisigAuthentication]
#     permission_classes = [IsCosigner]

#     def get(self, request, wallet_identifier=None):
#         qs = Signer.objects.all()
#         if wallet_identifier:
#             if wallet_identifier.isdigit():
#                 qs = qs.filter(wallet__id=wallet_identifier, wallet__deleted_at__isnull=True)
#             else:
#                 qs = qs.filter(wallet__locking_bytecode=wallet_identifier, wallet__deleted_at__isnull=True)

#         serializer = SignerSerializer(qs, many=True)
#         return Response(serializer.data)

#     def post(self, request, wallet_identifier=None):
#         # wallet_identifier is used for scoping, but wallet must also be included in POSTed data
#         data = request.data.copy()
#         if wallet_identifier and not data.get("wallet"):
#             # Auto-set the wallet field for convenience
#             if wallet_identifier.isdigit():
#                 wallet = get_object_or_404(MultisigWallet, id=wallet_identifier, deleted_at__isnull=True)
#             else:
#                 wallet = get_object_or_404(MultisigWallet, locking_bytecode=wallet_identifier, deleted_at__isnull=True)
#             data["wallet"] = wallet.id

#         serializer = SignerSerializer(data=data, context={"request": request})
#         if serializer.is_valid():
#             signer = serializer.save()
#             return Response(SignerSerializer(signer).data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class SignerDetailView(APIView):

#     authentication_classes = [PubKeySignatureMessageAuthentication, MultisigAuthentication]
#     permission_classes = [IsCosigner]

#     def get_object(self, signer_id):
#         try:
#             return Signer.objects.get(id=signer_id)
#         except Signer.DoesNotExist:
#             raise NotFound("Signer not found")

#     def get(self, request, signer_id):
#         signer = self.get_object(signer_id)
#         serializer = SignerSerializer(signer)
#         return Response(serializer.data)

#     def put(self, request, signer_id):
#         signer = self.get_object(signer_id)
#         serializer = SignerSerializer(signer, data=request.data, partial=True)
#         if serializer.is_valid():
#             signer = serializer.save()
#             return Response(SignerSerializer(signer).data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def delete(self, request, signer_id):
#         signer = self.get_object(signer_id)
#         signer.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)

# class MultisigWalletListCreateView(APIView):
    
#     authentication_classes = [PubKeySignatureMessageAuthentication, MultisigAuthentication]
    
#     def get_permissions(self):
#         if self.request.method == 'GET':
#             return [IsCosigner()]
#         elif self.request.method == 'POST':
#             return [IsCosignerOfNewMultisigWallet()]
#         else:
#             return super().get_permissions()

#     def get(self, request):
        
#         queryset = MultisigWallet.objects.filter(deleted_at__isnull=True)

#         include_deleted = request.query_params.get('include_deleted')

#         if include_deleted == '1' or include_deleted == 'true':
#             queryset = MultisigWallet.objects.all()
        
#         xpub = request.query_params.get('xpub')

#         if xpub:
#             queryset = queryset.filter(signers__xpub=xpub).distinct()

#         serializer = MultisigWalletSerializer(queryset, many=True)
#         return Response(serializer.data)

#     def post(self, request):
        
#         serializer = MultisigWalletSerializer(data=request.data, context={"request": request})
        
#         if serializer.is_valid():
#             wallet = serializer.save()
#             return Response(MultisigWalletSerializer(wallet).data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
# class MultisigWalletDetailView(APIView):
   
#     authentication_classes = [PubKeySignatureMessageAuthentication, MultisigAuthentication]
#     permission_classes = [IsCosigner]

#     def get(self, request, wallet_identifier):
#         try:
#             if wallet_identifier.isdigit():
#                 wallet = MultisigWallet.objects.get(id=wallet_identifier)
#             else:
#                 wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier)
#         except MultisigWallet.DoesNotExist:
#             raise NotFound(detail="Wallet not found.")
#         serializer = MultisigWalletSerializer(wallet)
#         return Response(serializer.data)
    
#     def delete(self, request, wallet_identifier):
#         permanently_delete = request.query_params.get('permanently_delete', False)
#         try:
#             if wallet_identifier.isdigit():
#                 identifier_name = 'id'
#                 wallet = MultisigWallet.objects.get(id=wallet_identifier)
#             else:
#                 identifier_name = 'locking_bytecode'
#                 wallet = MultisigWallet.objects.get(locking_bytecode=wallet_identifier)

#             if permanently_delete == 'true' or permanently_delete == '1':
#                 wallet.delete()
#             else:
#                 wallet.soft_delete()
#             return Response({"message": f"Wallet with {identifier_name}={wallet_identifier} deleted."}, status=status.HTTP_200_OK)

#         except MultisigWallet.DoesNotExist:
#             raise NotFound(detail="Wallet with {identifier_name}={identifier} Not Found.")
        
# class RenameMultisigWalletView(APIView):

#     authentication_classes = [PubKeySignatureMessageAuthentication, MultisigAuthentication]
#     permission_classes = [IsCosigner]

#     def patch(self, request, pk):
#         try:
#             wallet = MultisigWallet.objects.get(pk=pk)
#         except MultisigWallet.DoesNotExist:
#             return Response({"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND)

#         new_name = request.data.get("name")
#         if not new_name:
#             return Response({"detail": "Name field is required."}, status=status.HTTP_400_BAD_REQUEST)

#         # Django 3.0.14 requires full reassignment to track JSONField changes
#         template = wallet.template.copy()
#         template["name"] = new_name
#         wallet.template = template
#         wallet.save()

#         return Response({"id": wallet.id, "name": new_name}, status=status.HTTP_200_OK)

# class MultisigWalletUtxosView(APIView):
#     serializer_class = MultisigWalletUtxoSerializer
#     pagination_class = CustomLimitOffsetPagination
#     def get(self, request, address):
#         queryset = Transaction.objects.filter(spent=False, address__address=address)
        
#         only_tokens = request.query_params.get('only_tokens')
#         if only_tokens == 'true':     # return only token utxos
#             queryset = queryset.filter(Q(amount__gt=0) | Q(cashtoken_ft__category__isnull=False) | Q(cashtoken_nft__category__isnull=False))
        
#         token_type = request.query_params.get('token_type')
#         if token_type == 'ft':     # ft (may have capability also)
#             queryset = queryset.filter(Q(amount__gt=0) & Q(cashtoken_ft__category__isnull=False))

#         if token_type == 'nft':    # nft (may have ft also)
#             queryset = queryset.filter(Q(cashtoken_nft__category__isnull=False) & Q(cashtoken_nft__capability__isnull=False))

#         if token_type == 'hybrid': # strictly hybrid
#             queryset = queryset.filter(Q(amount__gt=0) & Q(cashtoken_ft__category__isnull=False) & Q(cashtoken_nft__category__isnull=False) & Q(cashtoken_nft__capability__isnull=False))

#         if token_type == 'nft' or token_type == 'hybrid':
#             capability = self.request.query_params.get('capability')
#             commitment = self.request.query_params.get('commitment')
#             commitment_ne = self.request.query_params.get('commitment_ne')
#             if capability:
#                 queryset = queryset.filter(cashtoken_nft__capability=capability)
#             if commitment:
#                 queryset = queryset.filter(cashtoken_nft__commitment=commitment)
#             if commitment_ne:
#                 queryset = queryset.filter(~Q(cashtoken_nft__commitment=commitment_ne))
#         category = request.query_params.get('category')
#         if category:
#             queryset = queryset.filter(~Q(cashtoken_nft__category=category))
        
#         paginate = request.query_params.get('paginate', False)
#         if paginate:
#             paginator = self.pagination_class()
#             page = paginator.paginate_queryset(queryset, request)
#             if page is not None:
#                 serializer = self.serializer_class(page, many=True)
#                 return paginator.get_paginated_response(serializer.data)
#         serializer = self.serializer_class(queryset, many=True)
#         return Response(serializer.data)

