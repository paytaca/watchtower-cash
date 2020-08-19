import pytest
import requests_mock
from main.models import BlockHeight
from tests.system.objects import obj_save_record
from tests.bch.objects import (
    obj_bitcoincashtracker,
    obj_latestblockheight
)

@pytest.mark.django_db
def test_bitcoincashtracker_transaction(requests_mock, monkeypatch, capsys):
    source = 'alt-bch-tracker'
    # Get the latest blockheight
    obj_latestblockheight.LatestBlockHeightTest(requests_mock).test()

    # The database should contain blockheight after checking the latest blockheight
    blockheight = BlockHeight.objects.first()
    assert blockheight

    # Through a given blockheight, we can test bitcoincashtracker from tasks.py
    script = obj_bitcoincashtracker.BitCoinCashTrackerTest(requests_mock, capsys, blockheight.id)
    script.test()


    # Test recording of Transaction
    outputs = getattr(script, 'output', None).split("\n")
    assert(outputs)
    for output in outputs:
        saving = obj_save_record.SaveRecordTest()
        args = saving.build_payload(output)
        if args:
            saving = obj_save_record.SaveRecordTest()
            saving.test(*args)
            assert saving.address == args[1]
            assert saving.txid == args[2]
            assert saving.amount == args[3]
            assert saving.source == args[4] == source
            assert saving.spent_index == args[6]