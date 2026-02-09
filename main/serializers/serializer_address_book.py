from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from main.models import AddressBook, AddressBookAddress, Wallet


class AddressBookAddressCreateSerializer(ModelSerializer):
    address_book_id = serializers.IntegerField(write_only=True, required=True)
    class Meta:
        model = AddressBookAddress
        fields = [
            'address',
            'address_type',
            'address_book_id'
        ]

    def create(self, validated_data):
        address_book_id = validated_data.pop('address_book_id', None)
        try:
            address_book = AddressBook.objects.get(id=address_book_id)
        except AddressBook.DoesNotExist:
            raise serializers.ValidationError({'address_book_id': 'Address book not found.'})
        validated_data['address_book'] = address_book
        return super().create(validated_data)

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

class AddressBookCreateSerializer(ModelSerializer):
    wallet_hash = serializers.CharField(max_length=70, write_only=True, required=True)

    class Meta:
        model = AddressBook
        fields = ['id', 'name', 'is_favorite', 'wallet_hash']

    def create(self, validated_data):
        wallet_hash = validated_data.pop('wallet_hash', None)
        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        except Wallet.DoesNotExist:
            raise serializers.ValidationError({'wallet_hash': 'Wallet not found.'})
        validated_data['wallet'] = wallet
        return super().create(validated_data)

class AddressBookSerializer(ModelSerializer):
    class Meta:
        model = AddressBook
        fields = '__all__'