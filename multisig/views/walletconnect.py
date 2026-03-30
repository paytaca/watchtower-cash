from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from multisig.models.wallet import MultisigWallet
from multisig.models.walletconnect import WalletConnectSession
from multisig.serializers.walletconnect import WalletConnectSessionSerializer
from multisig.auth.permission import IsCosigner


class WalletConnectSessionListCreateAPIView(APIView):

    def get_permissions(self):
        if self.request.method in ["POST", "PUT"]:
            return [IsCosigner()]
        return []

    def get_wallet(self, wallet_identifier):
        filter_q = Q(wallet_hash=wallet_identifier) | Q(
            wallet_descriptor_id=wallet_identifier
        )

        if type(wallet_identifier) == int or wallet_identifier.isdigit():
            filter_q = Q(id=wallet_identifier)

        return MultisigWallet.objects.filter(filter_q, deleted_at__isnull=True).first()

    def get(self, request, wallet_identifier):
        wallet = self.get_wallet(wallet_identifier)

        if not wallet:
            return Response(
                {"error": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND
            )

        sessions = WalletConnectSession.objects.filter(wallet=wallet).order_by(
            "-created_at"
        )
        serializer = WalletConnectSessionSerializer(sessions, many=True)
        return Response(serializer.data)

    def post(self, request, wallet_identifier):
        wallet = self.get_wallet(wallet_identifier)

        if not wallet:
            return Response(
                {"error": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = WalletConnectSessionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(wallet=wallet)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
