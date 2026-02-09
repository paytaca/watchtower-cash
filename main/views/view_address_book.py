from rest_framework import viewsets, mixins, status
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


class AddressBookViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin
):
    queryset = AddressBook.objects.all()
    serializer_class = AddressBookSerializer

    def get_queryset(self):
        return self.queryset.all()

    def get_object(self):
        return self.queryset.get(pk=self.kwargs['pk'])

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = AddressBookListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)

class AddressBookAddressViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin
):
    queryset = AddressBookAddress.objects.all()
    serializer_class = AddressBookAddressSerializer