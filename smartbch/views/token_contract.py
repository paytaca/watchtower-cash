from django.http import Http404
from rest_framework import viewsets, mixins

from smartbch.models import TokenContract
from smartbch.serializers import TokenContractSerializer
from smartbch.filters import TokenContractViewSetFilter
from smartbch.pagination import CustomLimitOffsetPagination


class TokenContractViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    lookup_field = "address"
    serializer_class = TokenContractSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokenContractViewSetFilter,
    ]

    def get_object(self):
        Model = self.serializer_class.Meta.model
        lookup_value = self.kwargs.get(self.lookup_field)
        try:
            instance = Model.objects.get(**{
                f"{self.lookup_field}__iexact": lookup_value,
            })
            return instance
        except Model.DoesNotExist:
            raise Http404
        except Model.MultipleObjectsReturned:
            pass

        return super().get_object()

    def get_queryset(self):
        return TokenContract.objects.all()
