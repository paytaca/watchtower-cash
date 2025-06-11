import logging

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from ..models.wallet import MultisigWallet
from ..serializers.wallet import MultisigWalletSerializer
LOGGER = logging.getLogger(__name__)

class MultisigWalletListCreateView(APIView):
    
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
   
    def get(self, request, identifier):
        try:
            if identifier.isdigit():
                wallet = MultisigWallet.objects.get(id=identifier)
            else:
                wallet = MultisigWallet.objects.get(locking_bytecode=identifier)
        except MultisigWallet.DoesNotExist:
            raise NotFound(detail="Wallet not found.")
        serializer = MultisigWalletSerializer(wallet)
        return Response(serializer.data)
    
    def delete(self, request, identifier):
        
        try:
            if identifier.isdigit():
                identifier_name = 'id'
                wallet = MultisigWallet.objects.get(id=identifier)
            else:
                identifier_name = 'locking_bytecode'
                wallet = MultisigWallet.objects.get(locking_bytecode=identifier)
            
            wallet.soft_delete()
            return Response({"message": f"Wallet with {identifier_name}={identifier} deleted."}, status=status.HTTP_200_OK)

        except MultisigWallet.DoesNotExist:
            raise NotFound(detail="Wallet with {identifier_name}={identifier} Not Found.")
        

class RenameMultisigWalletView(APIView):
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

class MultisigWalletDeleteAPIView(APIView):
     
   pass
