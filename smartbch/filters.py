from decimal import Decimal, InvalidOperation
from urllib.parse import unquote
from django.db import models
from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend

from smartbch.exceptions import InvalidQueryParameterException

class FilterBackendUtils:
    def _case_insensitive_list_filter(self, name="", values=[]):
        """
            Queryset filter builder for case insensitive filtering against list
        """
        _filter = models.Q()
        if not isinstance(values, list):
            return _filter

        field_name = f"{name}__iexact"        
        for value in values:
            _filter |= models.Q(**{
                field_name: value
            })
        return _filter

    def _parse_query_param(self, request, query_param, is_list=True, separator=",") -> (str, any):
        val = unquote(request.query_params.get(query_param, ""))
        if is_list:
            val = [v for v in val.split(separator) if v]
        return val


class TransactionTransferViewsetFilter(BaseFilterBackend, FilterBackendUtils):
    RECORD_TYPE_QUERY_NAME = "record_type"
    ADDRESSES_QUERY_NAME = "addresses"
    TOKEN_ADDRESSES_QUERY_NAME = "tokens"
    TRANSACTION_HASHES_QUERY_NAME = "txs"
    BEFORE_BLOCK_QUERY_NAME = "before_block"
    AFTER_BLOCK_QUERY_NAME = "after_block"


    def filter_queryset_by_address(self, request, queryset, view):
        record_type = self._parse_query_param(request, self.RECORD_TYPE_QUERY_NAME, is_list=False)
        addresses = self._parse_query_param(request, self.ADDRESSES_QUERY_NAME)

        if len(addresses):
            from_addr__iin = self._case_insensitive_list_filter(name="from_addr", values=addresses)
            to_addr__iin = self._case_insensitive_list_filter(name="to_addr", values=addresses)

            if record_type == "incoming":
                queryset = queryset.filter(to_addr__iin)
            elif record_type == "outgoing":
                queryset = queryset.filter(from_addr__iin)
            else:
                queryset = queryset.filter(
                    models.Q(from_addr__iin) | models.Q(to_addr__iin)
                )
        return queryset

    def filter_queryset_by_token_addresses(self, request, queryset, view):
        token_addresses = self._parse_query_param(request, self.TOKEN_ADDRESSES_QUERY_NAME)

        if len(token_addresses):
            token_contract__address__iin = self._case_insensitive_list_filter(
                name="token_contract__address",
                values=token_addresses
            )

            # "bch" is a special value for including transfers for BCH
            if "bch" in token_addresses:
                queryset = queryset.filter(
                    models.Q(token_contract__isnull=True) | models.Q(token_contract__address__iin)
                )
            else:
                queryset = queryset.filter(token_contract__address__iin)

        return queryset

    def filter_queryset_by_transactions(self, request, queryset, view):
        tx_hashes = self._parse_query_param(request, self.TRANSACTION_HASHES_QUERY_NAME)
        if len(tx_hashes):
            transaction__txid__iin = self._case_insensitive_list_filter(
                name="transaction__txid",
                values=tx_hashes
            )
            queryset = queryset.filter(transaction__txid__iin)

        return queryset

    def filter_queryset_by_block_range(self, request, queryset, view):
        before_block = self._parse_query_param(request, self.BEFORE_BLOCK_QUERY_NAME, is_list=False)
        after_block = self._parse_query_param(request, self.AFTER_BLOCK_QUERY_NAME, is_list=False)

        if before_block:
            try:
                parsed_before_block = Decimal(before_block)
                queryset = queryset.filter(transaction__block__block_number__lte=parsed_before_block)
            except InvalidOperation:
                raise InvalidQueryParameterException(f"Invalid value for {self.BEFORE_BLOCK_QUERY_NAME}: {before_block}")

        if after_block:
            try:
                parsed_after_block = Decimal(after_block)
                queryset = queryset.filter(transaction__block__block_number__gte=parsed_after_block)
            except InvalidOperation:
                raise InvalidQueryParameterException(f"Invalid value for {self.AFTER_BLOCK_QUERY_NAME}: {after_block}")

        return queryset

    def filter_queryset(self, request, queryset, view):
        queryset = self.filter_queryset_by_address(request, queryset, view)
        queryset = self.filter_queryset_by_token_addresses(request, queryset, view)
        queryset = self.filter_queryset_by_transactions(request, queryset, view)
        queryset = self.filter_queryset_by_block_range(request, queryset, view)

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
                "name": self.RECORD_TYPE_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.RECORD_TYPE_QUERY_NAME.capitalize(),
                "description": f"Values can be 'incoming', 'outgoing', or blank. Only meaning full with '{self.ADDRESSES_QUERY_NAME}' option",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.ADDRESSES_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.ADDRESSES_QUERY_NAME.capitalize(),
                "description": f"Filter by addresses separated by comma ','",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.TOKEN_ADDRESSES_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.TOKEN_ADDRESSES_QUERY_NAME.capitalize(),
                "description": f"Filter by token contracts addresses separated by comma ','. Accepts value 'bch' to include non token",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.TRANSACTION_HASHES_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.TRANSACTION_HASHES_QUERY_NAME.capitalize(),
                "description": f"Filter by transaction hashes separated by comma ','",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.BEFORE_BLOCK_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.BEFORE_BLOCK_QUERY_NAME.capitalize(),
                "description": f"Filter by transactions before the specified block number. The result is inclusive",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.AFTER_BLOCK_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.AFTER_BLOCK_QUERY_NAME.capitalize(),
                "description": f"Filter by transactions after the specified block number. The result is inclusive",
                "schema": {
                    "type": "string",
                }
            },
        ]


class TokenContractViewSetFilter(BaseFilterBackend, FilterBackendUtils):
    ADDRESSES_QUERY_NAME = "token_addresses"
    HAS_IMAGE_URL_QUERY_NAME = "has_image"
    TOKEN_TYPE_QUERY_NAME = "token_type"
    EXCLUDE_ADDRESSES_QUERY_NAME = "exclude_addresses"
    WALLET_ADDRESSES_QUERY_NAME = "wallet_addresses"

    def filter_queryset_by_address(self, request, queryset, view):
        addresses = self._parse_query_param(request, self.ADDRESSES_QUERY_NAME)
        address__in = self._case_insensitive_list_filter(name="address", values=addresses)
        queryset = queryset.filter(address__in)
        return queryset

    def filter_queryset_has_image_url(self, request, queryset, view):
        val = unquote(request.query_params.get(self.HAS_IMAGE_URL_QUERY_NAME, ""))

        parsed_value = None
        if val.lower() == "true":
            parsed_value = True
        elif val.lower() == "false":
            parsed_value = False

        # raise Exception(f"Parsed value: {parsed_value}")

        if parsed_value is not None:
            if parsed_value:
                queryset = queryset.filter(image_url__isnull=False, image_url__gte=0)
            else:
                queryset = queryset.filter(models.Q(image_url__isnull=True) | models.Q(image_url__lte=0))

        return queryset

    def filter_queryset_by_token_type(self, request, queryset, view):
        token_type = self._parse_query_param(request, self.TOKEN_TYPE_QUERY_NAME, is_list=False)
        if token_type:
            queryset = queryset.filter(token_type=token_type)
        return queryset

    def filter_queryset_by_exclude_addresses(self, request, queryset, view):
        exclude_addresses = self._parse_query_param(request, self.EXCLUDE_ADDRESSES_QUERY_NAME, is_list=True)
        if len(exclude_addresses):
            _exclude_addresses_filter = self._case_insensitive_list_filter(name="address", values=exclude_addresses)
            queryset = queryset.exclude(_exclude_addresses_filter)
        return queryset
    
    def filter_queryset_by_wallet_address(self, request, queryset, view):
        addresses = self._parse_query_param(request, self.WALLET_ADDRESSES_QUERY_NAME)
        if addresses:
            from_addr_filter = self._case_insensitive_list_filter(name="transfers__from_addr", values=addresses)
            to_addr_filter = self._case_insensitive_list_filter(name="transfers__to_addr", values=addresses)
            queryset = queryset.filter(models.Q(from_addr_filter | to_addr_filter)).distinct()
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
                "name": self.ADDRESSES_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.ADDRESSES_QUERY_NAME.capitalize(),
                "description": f"Filter by token addresses separated by comma ','",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.EXCLUDE_ADDRESSES_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.EXCLUDE_ADDRESSES_QUERY_NAME.capitalize(),
                "description": f"Exclude token addresses specified, separated by comma ','",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.HAS_IMAGE_URL_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.HAS_IMAGE_URL_QUERY_NAME.capitalize(),
                "description": f"Filter by tokens with or without image_urls",
                "schema": {
                    "type": "boolean",
                }
            },
            {
                "name": self.TOKEN_TYPE_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.TOKEN_TYPE_QUERY_NAME.capitalize(),
                "description": f"Filter by token type (e.g. '20', '721')",
                "schema": {
                    "type": "string",
                }
            },
            {
                "name": self.WALLET_ADDRESSES_QUERY_NAME,
                "required": False,
                "in": "query",
                "title": self.WALLET_ADDRESSES_QUERY_NAME.capitalize(),
                "description": f"Filter by transaction transfers on the addresses separated by comma ','",
                "schema": {
                    "type": "string",
                }
            },
        ]


    def filter_queryset(self, request, queryset, view):
        queryset = self.filter_queryset_by_address(request, queryset, view)
        queryset = self.filter_queryset_has_image_url(request, queryset, view)
        queryset = self.filter_queryset_by_token_type(request, queryset, view)
        queryset = self.filter_queryset_by_exclude_addresses(request, queryset, view)
        queryset = self.filter_queryset_by_wallet_address(request, queryset, view)

        return queryset
