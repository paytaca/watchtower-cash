from unittest import mock
from django.test import TestCase, tag
from smartbch.tests.mocker import response_values as mock_responses

import decimal
from main.models import Address

from smartbch.conf import settings as app_settings
from smartbch.models import Block
from smartbch.utils import block as block_utils

class BlockUtilsTestCase(TestCase):
    @tag("unit")
    def test_preload_block_range(self):
        num_of_blocks = 10
        (start_block, end_block, new_blocks) = block_utils.preload_block_range(0, num_of_blocks)
        # we have a +1 since the range is inclusive
        expected_new_blocks = num_of_blocks + 1
        self.assertEqual(
            len(new_blocks),
            expected_new_blocks,
            f"Expected new blocks to be {expected_new_blocks} but got {len(new_blocks)}",
        )

    @tag("unit")
    def test_preload_block_range_with_existing_in_range(self):
        num_of_blocks = 10
        Block.objects.create(block_number=decimal.Decimal(5))
        (start_block, end_block, new_blocks) = block_utils.preload_block_range(0, num_of_blocks)

        # we have a +1 since the range is inclusive
        # but since there is an existing block within the range, we subtract 1
        expected_new_blocks = num_of_blocks + 1 - 1
        self.assertEqual(
            len(new_blocks),
            expected_new_blocks,
            f"Expected new blocks to be {expected_new_blocks} but got {len(new_blocks)}",
        )
        new_block_numbers = {block.block_number for block in new_blocks}
        expected_new_blocks = set(range(int(start_block), int(end_block+1))) - { 5 }
        self.assertEqual(
            expected_new_blocks,
            new_block_numbers,
            f"Expected to new blocks to be {expected_new_blocks} but got {new_block_numbers}",
        )


    @tag("unit")
    def test_preload_new_blocks_empty_db(self):
        HARD_START_BLOCK = 0
        if isinstance(app_settings.START_BLOCK, (int, decimal.Decimal)):
            HARD_START_BLOCK = max(0, app_settings.START_BLOCK)

        mock_latest_block_number = HARD_START_BLOCK+20
        number_of_block_to_preload=10
        with mock.patch("web3.eth.Eth.block_number", new_callable=mock.PropertyMock(return_value=mock_latest_block_number)) as block_number_patch:
            (start_block, end_block, new_blocks) = block_utils.preload_new_blocks(blocks_to_preload=number_of_block_to_preload)
            self.assertEqual(len(new_blocks), number_of_block_to_preload + 1)
            self.assertEqual(end_block, mock_latest_block_number)
            self.assertEqual(start_block, mock_latest_block_number-number_of_block_to_preload)
            new_block_numbers = {block.block_number for block in new_blocks}
            expected_new_blocks = set(range(int(start_block), int(end_block+1)))
            self.assertEqual(
                expected_new_blocks,
                new_block_numbers,
                f"Expected to new blocks to be {expected_new_blocks} but got {new_block_numbers}",
            )

            self.assertTrue(
                Block.objects.filter(block_number=block_number_patch).exists(),
                f"Expected to create new block with number: {block_number_patch}",
            )
            return start_block, end_block

    @tag("unit")
    def test_preload_new_blocks_with_existing_preloaded(self):
        (prev_start_block_number, prev_end_block_number) = self.test_preload_new_blocks_empty_db()

        mock_latest_block_number = prev_end_block_number+20
        number_of_block_to_preload=20
        with mock.patch("web3.eth.Eth.block_number", new_callable=mock.PropertyMock(return_value=mock_latest_block_number)) as block_number_patch:
            (start_block, end_block, new_blocks) = block_utils.preload_new_blocks(blocks_to_preload=number_of_block_to_preload)
            self.assertEqual(len(new_blocks), number_of_block_to_preload)
            self.assertEqual(end_block, mock_latest_block_number)
            self.assertEqual(start_block, mock_latest_block_number-number_of_block_to_preload)
            new_block_numbers = {block.block_number for block in new_blocks}
            expected_new_blocks = set(range(int(start_block), int(end_block+1))) - { prev_end_block_number }
            self.assertEqual(
                expected_new_blocks,
                new_block_numbers,
                f"Expected to new blocks to be {expected_new_blocks} but got {new_block_numbers}",
            )

            self.assertTrue(
                Block.objects.filter(block_number=block_number_patch).exists(),
                f"Expected to create new block with number: {block_number_patch}",
            )
            return prev_start_block_number, end_block

    @tag("unit")
    def test_preload_new_blocks_with_existing_within_range(self):
        (prev_start_block_number, prev_end_block_number) = self.test_preload_new_blocks_with_existing_preloaded()

        # E.g. if latest block is 100, block #90 will be created before the preload and should not be in included in;
        # the test function's returned value
        mock_latest_block_number = prev_end_block_number+20
        number_of_block_to_preload=20
        existing_block_number = mock_latest_block_number - 10
        Block.objects.create(block_number=decimal.Decimal(existing_block_number))
        with mock.patch("web3.eth.Eth.block_number", new_callable=mock.PropertyMock(return_value=mock_latest_block_number)) as block_number_patch:
            (start_block, end_block, new_blocks) = block_utils.preload_new_blocks(blocks_to_preload=number_of_block_to_preload)
            self.assertEqual(len(new_blocks), number_of_block_to_preload-1)
            self.assertEqual(end_block, mock_latest_block_number)
            self.assertEqual(start_block, mock_latest_block_number-number_of_block_to_preload)
            new_block_numbers = {block.block_number for block in new_blocks}
            expected_new_blocks = set(range(int(start_block), int(end_block+1))) - { prev_end_block_number, existing_block_number }
            self.assertEqual(
                expected_new_blocks,
                new_block_numbers,
                f"Expected to new blocks to be {expected_new_blocks} but got {new_block_numbers}",
            )

            self.assertTrue(
                Block.objects.filter(block_number=block_number_patch).exists(),
                f"Expected to create new block with number: {block_number_patch}",
            )

    @tag("unit")
    def test_preload_new_blocks_response(self):
        HARD_START_BLOCK = 0
        if isinstance(app_settings.START_BLOCK, (int, decimal.Decimal)):
            HARD_START_BLOCK = max(0, app_settings.START_BLOCK)

        mock_latest_block_number = HARD_START_BLOCK+20

        with mock.patch("web3.eth.Eth.block_number", new_callable=mock.PropertyMock(return_value=mock_latest_block_number)) as block_number_patch:
            (start_block, end_block, new_blocks) = block_utils.preload_new_blocks()
            self.assertIsInstance(start_block, (int, decimal.Decimal))
            self.assertIsInstance(end_block, (int, decimal.Decimal))
            self.assertIsInstance(new_blocks, list)
            if len(new_blocks):
                self.assertIsInstance(new_blocks[0], Block)

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
