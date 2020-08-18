import pytest
import requests_mock
from tests.bch.objects import (
    obj_bitdbquery,
    obj_save_record,
)

@pytest.mark.django_db
def test_bitdbquery_transaction(requests_mock, monkeypatch, capsys):
    # Test BitDBQuery from tasks.py
    script = obj_bitdbquery.BitDBQueryTest(requests_mock, capsys)
    script.test()

    # Test recording of Transaction
    outputs = getattr(script, 'output', None).split("\n")
    assert(outputs)
    for output in outputs:
        args = [x.replace("'","").replace(")","").replace("(","").replace("None", "").strip() for x in output.split(',')]
        if len(output):
            saving = obj_save_record.SaveRecordTest()
            saving.test(*args)
            assert saving.txid == args[2]
            assert saving.address == args[1]
            if args[5] != '':
                assert saving.blockheight == args[5]