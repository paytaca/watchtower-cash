import pytest
import requests_mock
from tests.system.objects import obj_save_record
from tests.slp.objects import obj_slpdbtokenscanner


@pytest.mark.django_db
def test_slpdbtokenscanner_transaction(requests_mock, monkeypatch, capsys):
    # Testing Task
    source = 'slpdb_token_scanner'
    script = obj_slpdbtokenscanner.SLPDBTokenScannerTest(requests_mock, capsys)
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