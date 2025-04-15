from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import (
    MultisigWallet,
    Signer,
    Transaction,
    SignerTransactionSignature
)

from .serializers import (
    MultisigWalletSerializer,
    SignerSerializer,
    TransactionSerializer,
    SignerTransactionSignatureSerializer
)


class MultisigWalletListCreateView(APIView):
    def get(self, request):
        wallets = MultisigWallet.objects.all()
        serializer = MultisigWalletSerializer(wallets, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MultisigWalletSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MultisigWalletDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(MultisigWallet, pk=pk)

    def get(self, request, pk):
        wallet = self.get_object(pk)
        serializer = MultisigWalletSerializer(wallet)
        return Response(serializer.data)

    def put(self, request, pk):
        wallet = self.get_object(pk)
        serializer = MultisigWalletSerializer(wallet, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        wallet = self.get_object(pk)
        wallet.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class MultisigWalletTransactionListView(APIView):
    def get(self, request, wallet_id):
        # Filter transactions that were signed by signers in the given wallet
        transactions = Transaction.objects.filter(
            transaction_signatures__signer__wallet__id=wallet_id
        ).distinct()

        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
class SignerListCreateView(APIView):
    def get(self, request):
        signers = Signer.objects.all()
        serializer = SignerSerializer(signers, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SignerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SignerDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Signer, pk=pk)

    def get(self, request, pk):
        signer = self.get_object(pk)
        serializer = SignerSerializer(signer)
        return Response(serializer.data)

    def put(self, request, pk):
        signer = self.get_object(pk)
        serializer = SignerSerializer(signer, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        signer = self.get_object(pk)
        signer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TransactionListCreateView(APIView):
    def get(self, request):
        transactions = Transaction.objects.all()
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TransactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TransactionDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Transaction, pk=pk)

    def get(self, request, pk):
        transaction = self.get_object(pk)
        serializer = TransactionSerializer(transaction)
        return Response(serializer.data)

    def put(self, request, pk):
        transaction = self.get_object(pk)
        serializer = TransactionSerializer(transaction, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        transaction = self.get_object(pk)
        transaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TransactionSignaturesListView(APIView):
    def get(self, request, transaction_id):
        signatures = SignerTransactionSignature.objects.filter(transaction__id=transaction_id)
        serializer = SignerTransactionSignatureSerializer(signatures, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SignatureListCreateView(APIView):
    def get(self, request):
        signatures = SignerTransactionSignature.objects.all()
        serializer = SignerTransactionSignatureSerializer(signatures, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SignerTransactionSignatureSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SignatureDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(SignerTransactionSignature, pk=pk)

    def get(self, request, pk):
        signature = self.get_object(pk)
        serializer = SignerTransactionSignatureSerializer(signature)
        return Response(serializer.data)

    def put(self, request, pk):
        signature = self.get_object(pk)
        serializer = SignerTransactionSignatureSerializer(signature, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        signature = self.get_object(pk)
        signature.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SignerTransactionListView(APIView):
    def get(self, request, signer_id):
        # Filter transactions that were signed by the given signer
        transactions = Transaction.objects.filter(
            transaction_signatures__signer__id=signer_id
        ).distinct()

        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# X-Xpub: xpub6CUGRU...
# X-Message: authmsg:1713212123 <nonce>
# X-Signature: 45bcb3... (hex-encoded)
# X-Signature-Algo: schnorr
