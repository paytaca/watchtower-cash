from urllib.parse import unquote
from django.db.models import Q
from django.db.models import Exists, OuterRef
from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend

from main.models import Transaction

class TokensViewSetFilter(BaseFilterBackend):
    WALLET_HASH_QUERY_NAME = "wallet_hash"
    HAS_BALANCE_QUERY_NAME = "has_balance"
    EXCLUDE_TOKEN_IDS_QUERY_NAME = "exclude_token_ids"
    TOKEN_TYPE_QUERY_NAME = "token_type"

    def _parse_query_param(self, request, query_param, is_list=True, separator=",") -> (str, any):
        val = unquote(request.query_params.get(query_param, ""))
        if is_list:
            val = [v for v in val.split(separator) if v]
        return val

    def _case_insensitive_list_filter(self, name="", values=[]):
        """
            Queryset filter builder for case insensitive filtering against list
        """
        _filter = Q()
        if not isinstance(values, list):
            return _filter

        field_name = f"{name}__iexact"        
        for value in values:
            _filter |= Q(**{
                field_name: value
            })
        return _filter

    def filter_queryset_by_wallet_hash(self, request, queryset, view):
        wallet_hash = self._parse_query_param(request, self.WALLET_HASH_QUERY_NAME, is_list=False)
        has_balance = self._parse_query_param(request, self.HAS_BALANCE_QUERY_NAME, is_list=False)
        if has_balance.lower() == "true":
            has_balance = True
        elif has_balance.lower() == "false":
            has_balance = False
        else:
            has_balance = None

        if wallet_hash:
            queryset = queryset.filter(transaction__wallet__wallet_hash=wallet_hash)
            if has_balance is not None:
                # Since transaction amount will always be positive,
                # instead of using SUM operator against all transaction, we will only check if
                # the filtered wallet has(or doesnt have) any unspent transaction that has amount greater than zero,
                subquery = Transaction.objects.filter(
                    spent=False,
                    token_id=OuterRef('pk'),
                    amount__gte=0,
                )
                if has_balance:
                    queryset = queryset.filter(Exists(subquery))
                else:
                    queryset = queryset.filter(~Exists(subquery))

        queryset = queryset.distinct()

        return queryset


    def filter_queryset_by_exclude_token_ids(self, request, queryset, view):
        exclude_token_ids = self._parse_query_param(request, self.EXCLUDE_TOKEN_IDS_QUERY_NAME, is_list=True)
        if len(exclude_token_ids):
            _exclude_token_ids_filter = self._case_insensitive_list_filter(name="tokenid", values=exclude_token_ids)
            queryset = queryset.exclude(_exclude_token_ids_filter)
        return queryset

    def filter_queryset_by_token_type(self, request, queryset, view):
        token_type = self._parse_query_param(request, self.TOKEN_TYPE_QUERY_NAME, is_list=False)
        if token_type:
            queryset = queryset.filter(token_type=token_type)
        return queryset

    def filter_queryset(self, request, queryset, view):
        queryset = self.filter_queryset_by_wallet_hash(request, queryset, view)
        queryset = self.filter_queryset_by_exclude_token_ids(request, queryset, view)
        queryset = self.filter_queryset_by_token_type(request, queryset, view)

        return queryset

    def get_schema_fields(self, view):
        assert coreapi is not None, 'coreapi must be installed to use `get_schema_fields()`'
        assert coreschema is not None, 'coreschema must be installed to use `get_schema_fields()`'

        filter_fields= []
        for schema_param in self._get_schema_details(view):
            filter_fields.append(
                coreapi.Field(
                    name=schema_param["name"],
                    required=schema_param["required"],
                    location=schema_param["in"],
                    schema=coreschema.String(
                        title=schema_param["title"],
                        description=schema_param["description"],
                    )
                )
            )

        return filter_fields

    def get_schema_operation_parameters(self, view):
        return self._get_schema_details(view)

    def _get_schema_details(self, view):
        return [
            {
                "name": self.WALLET_HASH_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.WALLET_HASH_QUERY_NAME.capitalize(),
                "description": f"Filter tokens that have transactions related to the wallet hash",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.HAS_BALANCE_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.HAS_BALANCE_QUERY_NAME.capitalize(),
                "description": f"Meaningful only with `{self.WALLET_HASH_QUERY_NAME}`, filter tokens against wallet hash balance",
                "schema": {
                    "type": "boolean",
                }
            },
            {
                "name": self.EXCLUDE_TOKEN_IDS_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.EXCLUDE_TOKEN_IDS_QUERY_NAME.capitalize(),
                "description": f"Exclude tokenids separated by comma ','",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.TOKEN_TYPE_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.TOKEN_TYPE_QUERY_NAME.capitalize(),
                "description": f"Filter by token type",
                "schema": {
                    "type": "string",
                }
            },
        ]
