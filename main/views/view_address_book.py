from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from main.models import AddressBook, AddressBookAddress
from main.serializers import (
    AddressBookSerializer,
    AddressBookAddressSerializer,
    AddressBookListSerializer,
    AddressBookRetrieveSerializer,
    AddressBookCreateSerializer,

    AddressBookAddressCreateSerializer
)
from main.serializers.serializer_address_book import AddressBookUpdateSerializer


class AddressBookViewSet(
    viewsets.GenericViewSet,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin
):
    http_method_names = ['get', 'post', 'patch', 'delete']
    queryset = AddressBook.objects.all()
    serializer_class = AddressBookSerializer

    def get_queryset(self):
        return self.queryset.all()

    def get_object(self):
        return self.queryset.get(pk=self.kwargs['pk'])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = AddressBookRetrieveSerializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = AddressBookCreateSerializer(data=request.data.get('address_book'))
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        addresses = request.data.get('addresses')
        if addresses and isinstance(addresses, list) and len(addresses) > 0:
            for address in addresses:
                address['address_book_id'] = serializer.data['id']
                addresses_serializer = AddressBookAddressCreateSerializer(data=address)
                addresses_serializer.is_valid(raise_exception=True)
                addresses_serializer.save()
        
        return Response(serializer.data['id'], status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = AddressBookUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=['GET'],
        name='Get Wallet Address Book',
        url_path=r'wallet/(?P<wallet_hash>[^/.]+)'
    )
    def get_wallet_address_book(self, request, *args, **kwargs):
        queryset = self.queryset.filter(wallet__wallet_hash=kwargs.get('wallet_hash'))
        serializer = AddressBookListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class AddressBookAddressViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin
):
    queryset = AddressBookAddress.objects.all()
    serializer_class = AddressBookAddressSerializer