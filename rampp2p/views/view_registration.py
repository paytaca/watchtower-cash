from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rampp2p.models import RegistrationChallenge
from rampp2p.registration import (
    CHALLENGE_TTL, RegistrationThrottle, challenge_message, payload_digest, validate_identity,
)


class RegistrationChallengeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationThrottle]

    def post(self, request):
        account_type = request.data.get('account_type')
        wallet_hash = request.data.get('wallet_hash')
        public_key = request.data.get('public_key')
        validate_identity(wallet_hash, public_key)
        digest = payload_digest(account_type, wallet_hash, public_key, request.data.get('data'))
        challenge = RegistrationChallenge.objects.create(
            account_type=account_type, payload_digest=digest,
            expires_at=timezone.now() + CHALLENGE_TTL,
        )
        return Response({
            'challenge_id': str(challenge.pk), 'message': challenge_message(challenge),
            'expires_at': challenge.expires_at,
        }, status=status.HTTP_201_CREATED)
