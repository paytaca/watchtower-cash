from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from django.http import Http404
from django.db.models import Prefetch
from ..serializers.ad import AdSerializer
from ..models.ad import Ad

class AdList(APIView):
  def get(self, request):
    queryset = Ad.objects.all()

    serializer = AdSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  def post(self, request):
    # TODO: verify the signature
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
    serializer = AdSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdDetail(APIView):
  def get_object(self, pk):
    try:
      return Ad.objects.get(pk=pk)
    except Ad.DoesNotExist:
      raise Http404

  def get(self, request, pk):
    ad = self.get_object(pk)
    serializer = AdSerializer(ad)
    return Response(serializer.data, status=status.HTTP_200_OK)

  def put(self, request, pk):

    # TODO: verify the signature
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

    ad = self.get_object(pk)
    serializer = AdSerializer(ad, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
  def delete(self, request, pk):
    ad = self.get_object(pk)
    ad.is_deleted = True
    ad.deleted_at = timezone.now()
    return Response(status=status.HTTP_204_NO_CONTENT)