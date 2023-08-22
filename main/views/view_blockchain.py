from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from main.utils.queries.node import Node


class BlockChainView(APIView):

    def get(self, request, *args, **kwargs):
        node = Node()
        block_chain_info = node.BCH.get_block_chain_info()
        return Response(block_chain_info, status=status.HTTP_200_OK)
