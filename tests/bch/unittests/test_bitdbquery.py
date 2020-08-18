import pytest
import requests_mock
from tests.bch.objects import bitdbquery

@pytest.mark.django_db
def test_bitdbquery_transaction(requests_mock, monkeypatch, capsys):
    # Test BitDBQuery from tasks.py
    obj = bitdbquery.BitDBQueryTest(requests_mock, capsys)
    obj.test()