from django.http import Http404
from rest_framework import viewsets, mixins
from chat.serializers import PgpInfoSerializer, CreatePgpInfoSerializer


class PgpInfoViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.CreateModelMixin):
    lookup_field = "address"
    serializer_class = PgpInfoSerializer

    def get_serializer_class(self): 
        serializer_class = self.serializer_class 
        if self.request.method == 'POST': 
            serializer_class = CreatePgpInfoSerializer 
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
