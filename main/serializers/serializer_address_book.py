from rest_framework.serializers import ModelSerializer
from main.models import AddressBook, AddressBookAddress


class AddressBookSerializer(ModelSerializer):
    class Meta:
        model = AddressBook
        fields = '__all__'

class AddressBookAddressSerializer(ModelSerializer):
    class Meta:
        model = AddressBookAddress
        fields = '__all__'