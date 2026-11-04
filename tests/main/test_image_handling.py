"""Regression tests for callers of the untrusted-image helpers."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def image_file(name, fmt, size=(100, 50)):
    buffer = BytesIO()
    Image.new("RGB", size, "red").save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


@pytest.mark.django_db
def test_merchant_save_rejects_unsupported_logo(tmp_path, settings):
    from paytacapos.models import Merchant

    settings.MEDIA_ROOT = str(tmp_path)

    merchant = Merchant(
        wallet_hash="merchant-wallet-hash",
        name="TIFF Merchant",
        logo=image_file("logo.tiff", "TIFF"),
    )

    with pytest.raises(ValidationError):
        merchant.save()

    assert Merchant.objects.filter(wallet_hash="merchant-wallet-hash").count() == 0


def test_download_image_treats_unsupported_format_as_no_image(monkeypatch, settings, tmp_path):
    from main import tasks

    settings.TOKEN_IMAGES_DIR = str(tmp_path)
    tiff = image_file("token.tiff", "TIFF")

    monkeypatch.setattr(
        tasks.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            headers={"content-type": "image/tiff"},
            content=tiff.read(),
        ),
    )

    assert tasks.download_image("token-id", "https://example.com/token.tiff") == (200, None)
    assert list(tmp_path.iterdir()) == []


def test_upload_attachment_returns_400_for_unsupported_format(monkeypatch):
    from rampp2p import models
    from rampp2p.views.view_payment import OrderPaymentViewSet

    payment = SimpleNamespace(order=SimpleNamespace())

    class FakeOrderPaymentManager:
        def prefetch_related(self, *args, **kwargs):
            return self

        def get(self, **kwargs):
            return payment

    monkeypatch.setattr(models.OrderPayment, "objects", FakeOrderPaymentManager())

    view = OrderPaymentViewSet()
    monkeypatch.setattr(view, "_validate_awaiting_payment", lambda order: None)

    request = SimpleNamespace(FILES={"image": image_file("proof.tiff", "TIFF")})
    response = view.upload_attachment(request, pk=1)

    assert response.status_code == 400
    assert "Unsupported image format" in str(response.data["error"])
