import pytest
from tests.bch.objects.bitcoincashtracker import BitCoinCashTrackerTest
import requests_mock

def test_telegramBot_transaction(requests_mock, monkeypatch, capsys):
    obj = BitCoinCashTrackerTest(requests_mock, monkeypatch, capsys)
    captured = obj.test()
    assert captured.out == "aw\n"