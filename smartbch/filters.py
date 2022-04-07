from decimal import Decimal, InvalidOperation
from urllib.parse import unquote
from django.db import models
from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend

from smartbch.exceptions import InvalidQueryParameterException


class TransactionTransferViewsetFilter(BaseFilterBackend):
    RECORD_TYPE_QUERY_NAME = "record_type"
    ADDRESSES_QUERY_NAME = "addresses"
    TOKEN_ADDRESSES_QUERY_NAME = "tokens"
    TRANSACTION_HASHES_QUERY_NAME = "txs"
    BEFORE_BLOCK_QUERY_NAME = "before_block"
    AFTER_BLOCK_QUERY_NAME = "after_block"

    def __case_insensitive_list_filter(self, name="", values=[]):
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

    def filter_queryset_by_address(self, request, queryset, view):
        record_type = self._parse_query_param(request, self.RECORD_TYPE_QUERY_NAME, is_list=False)
        addresses = self._parse_query_param(request, self.ADDRESSES_QUERY_NAME)

        if len(addresses):
            from_addr__iin = self.__case_insensitive_list_filter(name="from_addr", values=addresses)
            to_addr__iin = self.__case_insensitive_list_filter(name="to_addr", values=addresses)

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
            token_contract__address__iin = self.__case_insensitive_list_filter(
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
            transaction__txid__iin = self.__case_insensitive_list_filter(
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
