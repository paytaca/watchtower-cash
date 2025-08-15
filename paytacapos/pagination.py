from collections import OrderedDict
from rest_framework import pagination, response


class CustomLimitOffsetPagination(pagination.LimitOffsetPagination):
    default_limit = 10
    max_limit = 50

    def get_paginated_response(self, data):
        return response.Response(OrderedDict([
            ('count', self.count),
            ('limit', self.limit),
            ('offset', self.offset),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'count': {
                    'type': 'integer',
                    'example': 123,
                },
                'limit': {
                    'type': 'integer',
                    'example': 10,
                },
                'offset': {
                    'type': 'integer',
                    'example': 0,
                },
                'next': {
                    'type': 'string',
                    'nullable': True,
                },
                'previous': {
                    'type': 'string',
                    'nullable': True,
                },
                'results': schema,
            },
        }


class WalletHistoryPageNumberPagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return response.Response(OrderedDict([
            ('page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('num_pages', self.page.paginator.num_pages),
            ('has_next', self.page.has_next()),
            ('history', data)
        ]))
