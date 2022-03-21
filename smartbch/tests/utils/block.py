from unittest import mock
from django.test import TestCase, tag
from smartbch.tests.mocker import response_values as mock_responses

from main.models import Address

from smartbch.conf import settings as app_settings
from smartbch.models import Block
from smartbch.utils import block as block_utils

class BlockUtilsTestCase(TestCase):
    @tag("unit")
    def test_preload_new_blocks(self):
        with mock.patch("web3.eth.Eth.block_number", new_callable=mock.PropertyMock(return_value=200)) as block_number_patch:
            (start_block, end_block) = block_utils.preload_new_blocks()
            self.assertEqual(start_block, app_settings.START_BLOCK or block_number_patch)
            self.assertEqual(end_block, block_number_patch)

            self.assertTrue(
                Block.objects.filter(block_number=block_number_patch).exists(),
                f"Expected to create new block with number: {block_number_patch}",
            )

        with mock.patch("web3.eth.Eth.block_number", new_callable=mock.PropertyMock(return_value=205)) as block_number_patch:
            (start_block, end_block) = block_utils.preload_new_blocks()
            self.assertEqual(start_block, 200)
            self.assertEqual(end_block, block_number_patch)

            self.assertEqual(
                Block.objects.filter(block_number__gte=200, block_number__lte=block_number_patch).count(),
                block_number_patch - 200 + 1, # need the plus 1 since it's inclusive
                f"Expected to have blocks from 200 to {block_number_patch}",
            )

    @tag("unit")
    def test_parse_block(self):
        with mock.patch("web3.eth.Eth.get_block", return_value=mock_responses.test_block_response) as block_patch:
            with mock.patch("web3.eth.Eth.get_logs", return_value=mock_responses.test_block_logs):
                block_obj = block_utils.parse_block(mock_responses.test_block_response.number, save_transactions=True)
                self.assertIsInstance(block_obj, Block)
                self.assertTrue(block_obj.processed)

    @tag("unit")
    def test_parse_block_with_tracked_addresses(self):
        Address.objects.get_or_create(
            address=mock_responses.test_block_response.transactions[0]['from'],
        )
        with mock.patch("web3.eth.Eth.get_block", return_value=mock_responses.test_block_response) as block_patch:
            with mock.patch("web3.eth.Eth.get_logs", return_value=mock_responses.test_block_logs):
                block_obj = block_utils.parse_block(mock_responses.test_block_response.number, save_transactions=True)
                self.assertIsInstance(block_obj, Block)
                self.assertTrue(block_obj.processed)
                self.assertEqual(
                    block_obj.transactions.count(),
                    len(block_patch.return_value.transactions),
                    f"Expected {block_obj} to have {len(block_patch.return_value.transactions)} transactions but got {block_obj.transactions.count()}",
                )
