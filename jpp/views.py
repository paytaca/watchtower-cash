import logging
from django.http import Http404
from rest_framework import (
    viewsets,
    mixins,
    decorators,
    parsers,
    renderers,
    exceptions,
)
from rest_framework.settings import api_settings
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from .models import Invoice
from .parser import (
    BComPaymentParser,
    BitPayPaymentOptionsParser,
    BitPayPaymentRequestParser,
    BitPayVerifyPaymentParser,
    BitPayPaymentParser,
    BComPaymentRequestParser,
)
from .renderers import (
    MediaTypes,
    BComPaymentRequestRenderer,
    BComPaymentACKRenderer,
    BitPayPaymentOptionsRenderer,
    BitPayPaymentRequestRenderer,
)
from .serializers import (
    InvoiceVerifySerializer,
    InvoiceSerializer,
    InvoicePaymentSerializer,
    BitpayPaymentRequestSerializer,
    BitPayPaymentSerializer,
)
from .utils.protobuf import (
    serialize_invoice,
    serialize_invoice_payment_ack,
)

LOGGER = logging.getLogger("main")


# Create your views here.
class InvoiceBaseView(APIView):
    def get_object(self):
        try:
            uuid = self.kwargs.get("uuid")
            return Invoice.objects.get(uuid=uuid)
        except Invoice.DoesNotExist:
            raise Http404("invoice not found")

    def get_accept_list(self):
        """
        Given the incoming request, return a tokenized list of media
        type strings.
        """
        header = self.request.META.get("HTTP_ACCEPT", "*/*")
        return [token.strip() for token in header.split(",")]

    def get_paypro_version(self):
        return self.request.META.get("HTTP_X_PAYPRO_VERSION", None)

    def get_content_type(self):
        header = self.request.META.get("CONTENT_TYPE", "")
        content_type_list = header.split(";")
        mimetype = content_type_list[0].strip()

        # not really used, but just for completeness
        encoding = None
        if len(content_type_list) > 1:
            encoding = content_type_list[1].strip().split("=")[1].strip()

        return mimetype

    def get_context(self):
        return {"request": self.request, "format": self.format_kwarg, "view": self}

class InvoiceBitPayView(InvoiceBaseView):
    parser_classes = (
        BitPayPaymentOptionsParser,
        BitPayPaymentRequestParser,
        BitPayVerifyPaymentParser,
        BitPayPaymentParser,
    )

    renderer_classes = [
        BitPayPaymentOptionsRenderer,
        BitPayPaymentRequestRenderer,
        renderers.TemplateHTMLRenderer,
        # renderers.JSONRenderer,
    ]

    def get_object_url(self):
        instance = self.get_object()
        return instance.get_absolute_uri(
            self.request,
            url_type=Invoice.URL_TYPE_BITPAY
        )

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_url = self.get_object_url()
        accepts = self.get_accept_list()
        if MediaTypes.BitPay.PaymentOptions in accepts:
            data = instance.payment_options(payment_url=instance_url)
            return Response(data=data)
        elif renderers.JSONRenderer.media_type in accepts:
            serializer = InvoiceSerializer(instance, context=self.get_context())
            return Response(serializer.data)
        elif renderers.TemplateHTMLRenderer.media_type in accepts:
            data = { "invoice": instance, "url": instance_url }
            return Response(data, template_name='jpp/invoice.html')
        raise exceptions.NotAcceptable()

    def post(self, request, *args, **kwargs):
        content_type = self.get_content_type()
        paypro_version = self.get_paypro_version()
        if paypro_version != "2":
            raise exceptions.UnsupportedMediaType(f"Expected version 2, got {paypro_version}")

        if MediaTypes.BitPay.PaymentRequest == content_type:
            return self.bitpay_payment_request()
        elif MediaTypes.BitPay.PaymentVerification == content_type:
            return self.bitpay_verify_payment()
        elif MediaTypes.BitPay.Payment == content_type:
            return self.bitpay_payment()

        return Response("Unsupported Content-Type for payment", status=400)

    def bitpay_payment_request(self):
        instance = self.get_object()
        serializer = BitpayPaymentRequestSerializer(data=self.request.data)
        if not serializer.is_valid() or serializer.validated_data["chain"] != "BCH":
            return Response("invalid payment option", status_code=400)

        data = instance.as_bitpay(payment_url=self.get_objet_url())
        LOGGER.info(f"PAYMENT REQUEST: {type(data)}: {data}")
        return Response(data)

    def bitpay_verify_payment(self):
        instance = self.get_object()
        serializer = BitPayPaymentSerializer(data=self.request.data, invoice=instance)
        if not serializer.is_valid():
            raise exceptions.ValidationError(
                "We were unable to parse your payment. Please try again or contact your wallet provider"
            )

        response_data = serializer.verify()
        return Response(response_data)

    def bitpay_payment(self):
        instance = self.get_object()
        serializer = BitPayPaymentSerializer(data=self.request.data, invoice=instance)
        if not serializer.is_valid():
            raise exceptions.ValidationError(
                "We were unable to parse your payment. Please try again or contact your wallet provider"
            )

        response_data = serializer.pay()
        return Response(response_data)


class InvoiceProtobufView(InvoiceBaseView):
    parser_classes = (
        BComPaymentParser,
    )

    renderer_classes = [
        BComPaymentRequestRenderer,
        BComPaymentACKRenderer,
        renderers.TemplateHTMLRenderer,
    ]

    def get_object_url(self):
        instance = self.get_object()
        return instance.get_absolute_uri(
            self.request,
            url_type=Invoice.URL_TYPE_BCOM
        )

    def get(self, request, *args, **kwargs):
        accepts = self.get_accept_list()
        instance = self.get_object()
        instance_url = self.get_object_url()

        if MediaTypes.BCom.PaymentRequest in accepts:
            payment_request_pb = serialize_invoice(instance, payment_url=instance_url)
            data = payment_request_pb.SerializeToString()
            return Response(data=data)
        elif renderers.JSONRenderer.media_type in accepts:
            serializer = InvoiceSerializer(instance, context=self.get_context())
            return Response(serializer.data)
        elif renderers.TemplateHTMLRenderer.media_type in accepts:
            data = { "invoice": instance, "url": instance_url }
            return Response(data, template_name='jpp/invoice.html')

        raise exceptions.NotAcceptable()

    def post(self, request, *args, **kwargs):
        accepts = self.get_accept_list()
        content_type = self.get_content_type()

        if MediaTypes.BCom.Payment != content_type:
            raise exceptions.UnsupportedMediaType(content_type)
        if MediaTypes.BCom.PaymentACK not in accepts:
            raise exceptions.NotAcceptable()

        instance = self.get_object()
        serializer = InvoicePaymentSerializer.from_protobuf(self.request.data, invoice=instance)
        try:
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
        except exceptions.APIException as error:
            errors = error.detail
            error_msg = "Unable to parse payment"
            if isinstance(errors, dict) and isinstance(errors.get("non_field_errors"), list) :
                errors = errors["non_field_errors"]

            if isinstance(errors, list) and len(errors):
                error_msg = errors[0]
            return Response(str(error_msg), status=400)

        instance.refresh_from_db()
        payment_ack_pb = serialize_invoice_payment_ack(instance.invoice)
        data = payment_ack_pb.SerializeToString()
        LOGGER.info(f"PAYMENT ACK: {type(data)}: {data}")
        return Response(data=data)


class InvoiceViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
):
    lookup_field = "uuid"
    serializer_class = InvoiceSerializer

    parser_classes = (
        parsers.JSONParser,
        BitPayPaymentOptionsParser,
        BitPayPaymentRequestParser,
        BComPaymentRequestParser,
    )

    renderer_classes = [
        BitPayPaymentOptionsRenderer,
        BitPayPaymentRequestRenderer,
        BComPaymentRequestRenderer,
        renderers.TemplateHTMLRenderer,
        *api_settings.DEFAULT_RENDERER_CLASSES,
    ]

    def get_accept_list(self):
        """
        Given the incoming request, return a tokenized list of media
        type strings.
        """
        header = self.request.META.get("HTTP_ACCEPT", "*/*")
        return [token.strip() for token in header.split(",")]

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.all()

    def retrieve(self, request, *args, **kwargs):
        accepts = self.get_accept_list()
        instance = self.get_object()
        if MediaTypes.BitPay.PaymentOptions in accepts:
            instance_url = instance.get_absolute_uri(
                self.request, url_type=Invoice.URL_TYPE_BITPAY,
            )
            data = instance.payment_options(payment_url=instance_url)
            return Response(data=data)
        elif MediaTypes.BCom.PaymentRequest in accepts:
            instance_url = instance.get_absolute_uri(
                self.request, url_type=Invoice.URL_TYPE_BCOM,
            )
            payment_request_pb = serialize_invoice(instance, payment_url=instance_url)
            data = payment_request_pb.SerializeToString()
            return Response(data=data)
        elif renderers.TemplateHTMLRenderer.media_type in accepts:
            instance_url = instance.get_absolute_uri(
                self.request, url_type=Invoice.URL_TYPE_BITPAY,
            )
            data = { "invoice": instance, "url": instance_url }
            return Response(data, template_name='jpp/invoice.html')

        return super().retrieve(request, *args, **kwargs)


    @swagger_auto_schema(method="post", request_body=InvoiceVerifySerializer, responses={200: InvoiceVerifySerializer, 400: InvoiceVerifySerializer})
    @decorators.action(methods=["post"], detail=True)
    def verify(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = InvoiceVerifySerializer(data=request.data, invoice=instance)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(serializer.data, status=200 if data["valid"] else 400)

    @swagger_auto_schema(method="post", request_body=InvoicePaymentSerializer, responses={200: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def pay(self, request, *args, **kwarg):
        instance = self.get_object()
        serializer = InvoicePaymentSerializer(invoice=instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response_serializer = self.get_serializer(serializer.instance.invoice)
        return Response(response_serializer.data)
