import pytest
import requests_mock
from main.models import BlockHeight
from tests.bch.objects import (
    obj_bitcoincashtracker,
    obj_latestblockheight
)

@pytest.mark.django_db
def test_bitcoincashtracker_transaction(requests_mock, monkeypatch, capsys):
    # Get the latest blockheight
    obj_latestblockheight.LatestBlockHeightTest(requests_mock).test()

    # The database should contain blockheight after checking the latest blockheight
    blockheight = BlockHeight.objects.first()
    assert blockheight

    # Through a given blockheight, we can test bitcoincashtracker from tasks.py
    obj = obj_bitcoincashtracker.BitCoinCashTrackerTest(requests_mock, capsys, blockheight.id)
    obj.test()