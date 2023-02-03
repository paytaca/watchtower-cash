# JSON Payment Protocol
Watchtower's API for BIP70 payments

## API
- POST:`/jpp/invoices/`
  - create an invoice in watchtower
- GET: `/jpp/invoices/{uuid}/`
  - retrieves a single invoice
- POST: `/jpp/invoices/{uuid}/verify`
  - verify an unsigned transaction if it satifies the required amount for each output address 
- POST: `/jpp/invoices/{uuid}/pay`
  - submit a signed transaction hex as payment to an invoice
  - broadcasts & saves the tx hex to db
  - validates the transaction hex before broadcasting
- GET, POST: `jpp/i/{uuid}/`
  - APIs that follow Bitcoin.com's implementation
- GET, POST: `jpp/i/bitpay/{uuid}/`
  - APIs that follow Bitpay's implementation
