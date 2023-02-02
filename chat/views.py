from django.http import Http404
from django.db.models import Q
from rest_framework import viewsets, mixins, generics
from chat.serializers import (
    ChatIdentitySerializer,
    CreateChatIdentitySerializer,
    ConversationSerializer
)


class ChatIdentityViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.CreateModelMixin):
    lookup_field = "address"
    serializer_class = ChatIdentitySerializer

    def get_serializer_class(self): 
        serializer_class = self.serializer_class 
        if self.request.method == 'POST': 
            serializer_class = CreateChatIdentitySerializer 
        return serializer_class

    def get_object(self):
        Model = self.serializer_class.Meta.model
        lookup_value = self.kwargs.get(self.lookup_field)
        try:
            instance = Model.objects.get(**{
                f"address__{self.lookup_field}__iexact": lookup_value,
            })
            return instance
        except Model.DoesNotExist:
            raise Http404
        except Model.MultipleObjectsReturned:
            pass

        return super().get_object()


class ConversationView(generics.ListAPIView):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        address = self.kwargs['address']
        Model = self.serializer_class.Meta.model
        return Model.objects.filter(Q(from_address__address=address) | Q(to_address__address=address))
