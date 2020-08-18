import pytest
import requests_mock
from tests.bch.objects import obj_bitsocket

@pytest.mark.django_db
def test_bitdbquery_transaction(requests_mock, capsys):
    # Test BitDBQuery from tasks.py
    obj = obj_bitsocket.BitSocketTest(requests_mock, capsys)
    obj.test()