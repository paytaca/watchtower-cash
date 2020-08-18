import pytest
import requests_mock
from tests.bch.objects import obj_bitdbquery

@pytest.mark.django_db
def test_bitdbquery_transaction(requests_mock, monkeypatch, capsys):
    # Test BitDBQuery from tasks.py
    obj = obj_bitdbquery.BitDBQueryTest(requests_mock, capsys)
    obj.test()