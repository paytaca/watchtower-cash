from rest_framework.serializers import ModelSerializer, SerializerMethodField
from main.models import AddressBook, AddressBookAddress

class AddressBookListSerializer(ModelSerializer):
    address_count = SerializerMethodField()

    def get_address_count(self, obj):
        return obj.address_book_addresses.count()

    class Meta:
        model = AddressBook
        fields = [
            'id',
            'name',
            'is_favorite',
            'address_count'
        ]

class AddressBookAddressSerializer(ModelSerializer):
    class Meta:
        model = AddressBookAddress
        fields = [
            'id',
            'address',
            'address_type',
        ]
class AddressBookRetrieveSerializer(ModelSerializer):
    addresses = SerializerMethodField()

    def get_addresses(self, obj):
        return AddressBookAddressSerializer(obj.address_book_addresses.all(), many=True).data

    class Meta:
        model = AddressBook
        fields = [
            'id',
            'name',
            'is_favorite',
            'created_at',
            'addresses'
        ]

class AddressBookSerializer(ModelSerializer):
    class Meta:
        model = AddressBook
        fields = '__all__'