# Anyhedge
Watchtower's API for managing anyhedge contracts

## API
List views are always paginated by limit-offset, defaults to limit=10,offset=0
### HedgePosition - `/anyhedge/hedge-position/.*`
  - List, Create, & Detail view: uses rest-framework's default. Detail view accepts `address` instead of `id`
  - POST:`/fund_gp_lp_contract/`
    - performs the last step of creating hedge contracts with *General Protocol*'s liquidity provider which is to submit funding utxo to GP's API; 
    - then saves the contract in the server
  - POST:`/submit_funding_proposal/`
    - Submit a utxo for the contract's funding
    - This API will attempt to broadcast the funding transaction if funding utxo for both hedge and long are present. See `complete_contract_funding` task below.
    - Used for generated contracts through P2P 
    - Fails silently, or will not return an error, if fails to broadcast funding.
  - POST:`/{address}/complete_funding/`
    - Attempts to broadcast a funding transaction from the contract's submitted funding proposal, if exists.
    - See `complete_contract_funding` task below.
    - Used for generated contracts through P2P 
  - POST:`/{address}/validate_contract_funding/`
    - See `validate_contract_funding` task below
  - GET:`/summary/`
    - Returns aggregated data of hedge contracts, given the filter parameters provided.
    - Returns the total nominal unit of hedge side, grouped by oracle_pubkey/asset.
    - Returns total satoshis of long side, grouped by oracle_pubkey/asset.
  - POST: `{address}/mutual_redemption/`
    - Used for creating a mutual redemption offer
    - Optionally pass signatures for the payout transaction.
    - Will proceed to broadcast the payout transaction if signatures of both parties are present. See `redeem_contract` task below.
    - Currently for generated contracts through P2P only
  - POST: `{address}/complete_mutual_redemption/`
    - See `redeem_contract` task below
    - Currently for generated contracts through P2P only
### Oracles & Price messages
  - `/anyhedge/oracles/`
    - provide a list of oracles saved in the db. provides oracles pubkey and asset info(asset name, currency, & decimals).
  - `/anyhedge/oracles/{pubkey}/`
    - retrieve a single oracle
  - `/anyhedge/price-messages/`
    - provides a list of oracle price messages, can be filtered by `pubkey`, `timestamp`(range), `price_sequence`(range), and/or `message_sequence`(range)
### HedgePositionOffer - `/anyhedge/hedge-position-offers/.*`
  - List view: rest-framework's default, can be filtered by `wallet_hash`, `exclude_wallet_hash`, `statuses`
  - Create view: 
    - rest-framework's default
  - POST:`/find_match/` - finds a matching hedge position offer given a set of parameters
    - if there is no suitable match, it will return a list of offers that is similar to the expected match
  - POST: `{id}/accept_offer/`
    - used for accepting an existing hedge position offer created by other users
    - the request payload will contain the other information needed to compile a contract in 
    - the accepted offer's status will be set to "accepted"
    - while the offer is in "accepted" state, the offer will not be matched in the `/find_match/` endpoint
    - there will be a `settlement_deadline` where the user that accepted the offer must settle the offer by providing its funding utxo(through `{id}/settle_offer/` API)
  - POST:`/{id}/settle_offer/`
    - to settle an offer, the offer must be in "accepted" state
    - the request payload must contain the funding utxo for the counterparty
    - will create a hedge position from the HedgePositionOffer instance and its HedgePositionOfferCounterParty info
    - will update the offer's status to "settled"
    - "settled" offers no longer be used in the `/find_match/` endpoint

### Other endpoints
  - Websocket updates `ws/anyhedge/updates/{wallet_hash}/$`
    - Sends messages for a `wallet_hash` to update changes in the contracts
    - Messages are generally in the following structure:
    ```
    { "resource": <string>, "action": <string>, "meta": <any> }
    ```

---------------

## Background tasks
### Scheduled tasks
  - `update_oracle_prices` - `anyhedge.tasks.check_new_price_messages`
    - Retrieves the latest price messages of oracles saved in db.
    - `check_new_price_messages()` task retrieves list of oracle pubkeys, then calls new task `check_new_oracle_price_messages(oracle_pubkey)`
    - `check_new_oracle_price_messages` will retrieve at most 10 latest price messages of an oracle. It will check the latest price timestamp saved in db and reduce the number of price messages accordingly to `(latest_timestamp - current_timestamp) / 60 seconds` as new price messages are generated per minute.

  - `update_anyhedge_contract_settlements` - `anyhedge.tasks.update_matured_contracts`
    - The contracts handled if the apply to the following conditions:
      - contract is funded
      - no settlement transaction saved in db
      - maturity_timestamp is less than current timestamp
    - Contracts will be passed to either subtasks:
      - `update_contract_settlement_from_service`: if the contract has a settlement service (Accessed through `HedgePosition.settlement_service`)
      - `settle_contract_maturity`: if the contract has no `settlement_service`, implying the contract should be settled by the server.

  - `update_anyhedge_contracts_for_liquidation` - `anyhedge.tasks.update_contracts_for_liquidation`
    - Checks for unsettled & funded contracts that are valid for liquidation. More details in `anyhedge.utils.settlement.get_contracts_for_liquidation()` function.
    - Retrieved contracts are passed to `liquidate_contract(contract_address, message_sequence)` task

### Other tasks - `anyhedge.tasks.*`
  - `update_contract_settlement`
    - Main task for updating and saving a contract's settlement data, will either call `update_contract_settlement_from_service` or `update_contract_settlement_from_chain`.

  - `update_contract_settlement_from_service(address)`
    - Uses `anyhedge.utils.contract.get_contract_status` to get the contract's status directly from its settlement service, if exists, then saves the data to db.
  - `update_contract_settlement_from_chain(address)`
    - Searches for the contract's settlement tx in the blockchain using `anyhedge.utils.settlement.search_settlement_tx` function, then saves the data to db, if exists.

  - `complete_contract_funding`
    - The task for submitting/broadcasting the funding transaction of a contract.
    - Uses `anyhedge.utils.funding.search_funding_tx` function to search for the funding transaction in the blockchain before proceeding in case it exists but wasnt saved in db. 

  - `validate_contract_funding`
    - Uses `anyhedge.utils.funding.validate_funding_transaction` to search for the funding tx of a contract in the blockchain.
    - If the tx exists, it will save the data: `funding_output`, `funding_satoshis`, `fee_output` `fee_satoshis` to `HedgePositionFunding` model. Then flag the contract's funding transaction as valid.

  - `redeem_contract`
    - The task for creating and broadcasting the mutual redemption transaction of a contract.
    - Before proceeding, it will check if the contract is already settled by checking the db or using the `update_contract_settlement` task

------
## Other
### JS scripts
- Anyhedge app takes advantage of functions from `@generalprotocol/anyhedge` library to:
  - compiling anyhedge contract, which generates the contract address, parameters, and metadata.
  - generating the funding transaction from the given utxos, also has transaction checks to validate that the utxos' satoshis are valid
  - parsing settlement data from raw transactions.
  - generating the settlement transaction for all cases(maturation, liquidation, mutual redemption), also checks the validity of data (e.g. price messages, & payout satoshis that each party gets)
  - fetching, validated, and parsing oracle price messages.
- `anyhedge.js.runner.AnyhedgeFunctions`
  - JS functions from the `anyhedge.js.src.funcs` are loaded into `anyhedge.js.runner.AnyhedgeFunctions` class to provide an abstraction on running them.
  - Functions are loaded by running `anyhedge.js.src.load.js` which returns the function names.
  - Functions in `anyhedge.js.runner.AnyhedgeFunctions` accept will only accept _positional arguments_ that are JSON serializable

### HedgePositionOffer lifecycle
NOTE: `settled` status for `HedgePositionOffer` only implies that the offer has an `HedgePosition` created
1. User1 creates a `HedgePositionOffer`, by default the status is `pending`
    - The created position offer will be part of the pool in `/anyhedge/hedge-position-offers/find_match/` API
2. Other users (e.g. User2) can accept the offer created by User1. User2 accepts User1’s offer by providing his `pubkey`, `address`, & `wallet_hash`. The server then gets the latest price of the oracle pubkey (from User1’s offer) and proceeds to construct a contract to save the contract address. After this, the status of the offer is changed to `accepted`
3. After the offer is changed to `accepted`, a settlement deadline is set (a fixed duration after accepting the offer). The counter party(User2) can check the contract details (in the app) to verify.
    1. If the counter party chooses to continue, the counter party(User2) must then provide a funding UTXO to settle the offer.
    2. If not, the counter party(User2) can cancel accepting the position offer which will revert the position offer into a `pending` state(returning it back in the pool for finding match). This can be skipped & will automatically be reverted after the settlement deadline.
4. After the counter party(User2) submits a funding UTXO, a `HedgePosition` instance is created using the offer’s data then the offer instance’s status is changed to `settled`
