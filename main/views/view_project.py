from rest_framework import viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response

from main.models import Project, WalletHistory
from main.serializers import (
    ProjectSerializer,
    PaginatedProjectLeaderboardSerializer,
    ProjectWalletsSerializer,
)

from datetime import timedelta

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.db.models import *
from django.utils import timezone
from django.core.paginator import Paginator


class ProjectViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class ProjectWalletsView(APIView):

    @swagger_auto_schema(
        responses={ 200: ProjectWalletsSerializer },
        manual_parameters=[
            openapi.Parameter(name="active", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
            openapi.Parameter(name="active_days_threshold", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, default=30),
        ]    
    )
    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id', None)
        active_days_threshold = request.query_params.get('active_days_threshold', 30)
        active = request.query_params.get('active', False)
        active = active.strip().lower() == 'true'
        
        transactions = WalletHistory.objects.filter(wallet__project_id=project_id)

        if active:
            transactions = transactions.annotate(
                threshold_date=ExpressionWrapper(
                    F('date_created') + timedelta(days=active_days_threshold),
                    output_field=DateTimeField()
                )
            )
            transactions = transactions.filter(threshold_date__gt=timezone.now())
        
        transactions = transactions.annotate(wallet_hash=F('wallet__wallet_hash'))
        transactions = transactions.order_by('wallet_hash').distinct('wallet_hash')
        data = transactions.values_list('wallet_hash', flat=True)
        return Response({ 'wallets': data })


class ProjectLeaderboardView(APIView):

    @swagger_auto_schema(
        responses={ 200: PaginatedProjectLeaderboardSerializer },
        manual_parameters=[
            openapi.Parameter(name="page", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, default=1),
            openapi.Parameter(
                name="ordering",
                type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY,
                default="-transactions_total_count",
                enum=[
                    "transactions_total_count", "incoming_transactions", "outgoing_transactions",
                    "-transactions_total_count", "-incoming_transactions", "-outgoing_transactions",
                ]
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id', None)
        page = request.query_params.get('page', 1)
        ordering = request.query_params.get('ordering', '-transactions_total_count')
        project = Project.objects.get(id=project_id)
        integer_field = IntegerField()

        transactions = WalletHistory.objects.filter(
            wallet__project_id=project.id
        ).annotate(
            wallet_hash=F('wallet__wallet_hash')
        )
        transactions = transactions.values('wallet_hash')
        transactions = transactions.annotate(
            transactions_total_count=Count('wallet_hash'),
            incoming_transactions=Count( Case(When(record_type='incoming', then=1), output_field=integer_field) ),
            outgoing_transactions=Count( Case(When(record_type='outgoing', then=1), output_field=integer_field) )
        )
        transactions = transactions.order_by(ordering)

        pages = Paginator(transactions, 10)
        page_obj = pages.page(int(page))
        data = {
            'leaderboard': page_obj.object_list,
            'page': page,
            'num_pages': pages.num_pages,
            'has_next': page_obj.has_next()
        }
        return Response(data=data)