import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound

from multisig.auth.auth import PubKeySignatureMessageAuthentication, parse_signatures
from multisig.models.auth import ServerIdentity
from multisig.serializers.auth import ServerIdentitySerializer
from multisig.js_client import verify_signature

LOGGER = logging.getLogger(__name__)

class ServerIdentityListCreateView(APIView):
    
    authentication_classes = [PubKeySignatureMessageAuthentication]
    
    def get(self, request):
        
        queryset = ServerIdentity.objects.filter(deleted_at__isnull=True)

        include_deleted = request.query_params.get('include_deleted')

        if include_deleted == '1' or include_deleted == 'true':
            queryset = ServerIdentity.objects.all()

        serializer = ServerIdentitySerializer(queryset, many=True)

        return Response(serializer.data)

    def post(self, request):
        
        public_key = request.data.get('publicKey') or request.data.get('public_key')
        signature = parse_signatures(request.data.get('signature'))
        sig_verification_response = verify_signature(request.data.get('message'), public_key, signature)
        sig_verification_result = sig_verification_response.json()  
        
        if not sig_verification_result['success']:
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        
        if public_key:
            existing = ServerIdentity.objects.filter(public_key=public_key, deleted_at__isnull=True).first()
            if existing:
                response_data = ServerIdentitySerializer(existing).data
                return Response(response_data, status=status.HTTP_200_OK)

        serializer = ServerIdentitySerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            server_identity = serializer.save()            
            response_data = ServerIdentitySerializer(server_identity).data
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServerIdentityDetailView(APIView):

    authentication_classes = [PubKeySignatureMessageAuthentication]

    def _include_deleted(self, request):
        include_deleted = request.query_params.get('include_deleted')
        if include_deleted is None:
            return False
        return include_deleted.lower() in ('1', 'true')

    def _get_object(self, public_key, include_deleted=False):
        queryset = ServerIdentity.objects.all()
        if not include_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)
        server_identity = queryset.filter(public_key=public_key).first()
        if not server_identity:
            raise NotFound('Server identity not found')
        return server_identity

    def get(self, request, public_key):
        include_deleted = self._include_deleted(request)
        server_identity = self._get_object(public_key, include_deleted)
        serializer = ServerIdentitySerializer(server_identity)
        return Response(serializer.data)
