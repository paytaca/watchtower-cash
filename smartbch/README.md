# Watchtower (Smart BCH chain)
## Settings
Settings can be set in `settings.py`. Default values are in `smartbch/conf.py`:
```
SMARTBCH = {
    "START_BLOCK": None,
    "BLOCK_TO_PRELOAD": None,
    "BLOCKS_PER_TASK": 50,
    "JSON_RPC_PROVIDER_URL": "https://smartbch.fountainhead.cash/mainnet",
}
```
### `START_BLOCK`
A marker for not parsing blocks before the specified start block. If the value is `None`, automatically implies 0.

### `BLOCK_TO_PRELOAD`
Specifies the blocks to preload relative to the latest block. See `Main loop` below for more info. 

### `BLOCKS_PER_TASK`
Specifies the number of preloaded blocks to parse per task. See `Main loop` below for more info.

#### `JSON_RPC_PROVIDER_URL`
- URL of provider used. Blockchain data is taken from this url. 
- When changing provider url, must ensure that it is of the same chain id since current implementation assumes it's storing for a single chain only. (SmartBCH main chain in this case).

## Models
```
Block:
    block_number: decimal
    timestamp: timestamp
    tx_count: int

TokenContract:
    address: address
    name: string
    symbol: string
    token_type: number: { 20, 721 }

Transaction:
    block_number: Block
    txid: hex_string (32 bytes)
    from_addr: address
    to_addr: address
    data: hex_string
    value: decimal

TransactionTransfer:
    transaction: Transaction
    log_index: int | None
    token_contract: TokenContract | None
    from_addr: address
    to_addr: address
    amount: decimal
    status: int: { 0, 1 }
    processed_transfers: boolean

TransactionTransferReceipientLog:
    transaction_transfer: TransactionTransfer
    subscription: main.Subscription
    sent_at: timestamp
```

## Parsing the chain

The watchtower watches for new blocks and transactions and saves transfers of assets: BCH, any ERC20 & ERC721 tokens.
### Main loop

1. Preload new blocks to database
    - Only block numbers are saved in the database in this step and flagged `processed=False`.
    - Saved block numbers are in range `(latest - BLOCK_TO_PRELOAD, latest)`. However if `latest - BLOCK_TO_PRELOAD` is less than zero or `START_BLOCK`, the start number of the range will be changed accordingly.
    - `BLOCK_TO_PRELOAD` is set to limit db operations per iteration. Potential missed blocks due to this limit are handled by another task. See `Fallback processes` below for more info. 
    - Main function is at `tasks.preload_new_blocks_task`. Run by celery beat for every 20 seconds.
2. Parse blocks
    - Looks for preloaded blocks that are flagged `processed=False`.
    - Parse individual blocks and saves other data about the block (e.g. timestamp, tx_count).
    - A max number of blocks to process per iteration is placed to limit burst network usage. The max number of blocks is determined by settings `BLOCKS_PER_TASK`.
    - Saves the transactions if the transaction contains any subscribed address. Also checks the addresses of emmitted `Transfer` events for ERC20 & ERC721.
    - Main task is at `tasks.parse_blocks_task`. Run by celery beat for every 30 seconds
3. Parse transaction transfers
    - A single transaction can have multiple transfer of tokens and BCH. Hence, they stored separately in the `TransactionTransfer` model.
    - Main function is at `tasks.save_transaction_transfers_task`. Run through other tasks (e.g. `tasks.parse_blocks_task`)

### Subscription

Uses the main app's subscription model. After parsing transaction transfers in the main loop, they are passed to a task `tasks.send_transaction_transfer_notification_task`.
    - Each `models.TransactionTransfer` notification sent to a subscription is logged through: `models.TransactionTransferReceipientLog`.
    - The tasks only sends to subscriptions that have not yet been sent. Unsent notifications are resolved through `models.TransactionTransfer.get_unsent_valid_subscriptions()` 


### Fallback processes

In case the server goes down or stops midway, the main block parser tasks still handles the more recent blocks and ignores the earlier blocks. A periodic task is in place for handling missing block numbers.

- `tasks.parse_missing_blocks_task`
    - The task preloads missing block numbers between the min and max saved block number in db. Missing blocks are resolved through `models.Block.get_missing_block_numbers()` function.
    - Also saves the transactions and transaction transfers under the found missing blocks. 
- `tasks.handle_transactions_with_unprocessed_transfers_task`
    - Looks for transactions without saved transactions transfers and parse them.
    - Notifications for `TransactionTransfer` are sent if the block's age is less than 1 hour.

#### Other

- `models.TokenContract` are expected to have metadata (e.g. name & symbol). They are populated through the following events:
    - when sending notification for a `models.TransactionTransfer`. 
    - a periodic task `tasks.parse_token_contract_metadata_task` that runs every 5 minutes. Can only parse 10 token contracts per call.
