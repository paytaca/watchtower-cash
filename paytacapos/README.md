# POS Device linking flow
1. (Main app) Generate link code using `/devices/generate_link_device_code/` api
    - get wallet `xpubkey`, `wallet_hash`, & `posid`
    - create random `encrypt_key` to encrypt `xpubkey` using any cryptographic algorithm. (Main app & POS app must use the same algorithm)
    - create random `nonce` & sign `encrypted_xpubkey` using keypair of wallet at index `nonce`
    - Pass the data `wallet_hash`, `posid`, `encrypted_xpubkey`, & `signature` to api.
    - api returns `link_code` and `expires` timestamp
2. (Main app) Show the QR code for POS device to scan
    - Include the data `link_code`, `nonce`, and a `decrypt_key` for `encrypted_xpubkey`
3. (POS app) Preparing link device data
    - Device scans the QR code from the Main app
    - Device retrieves `encrypted_xpubkey` from server through `/devices/link_code_data/` api
    - Decrypt `xpubkey`, using `decrypt_key` from the QR code
    - Generate pubkey from `xpubkey` using index `nonce`
4. (POS app) Complete link flow using `/devices/redeem_link_device_code/` api
    - Device compiles device info. `device_id`, `name`, `device_model`, `os`. Data is based from quasar's `Device` capacitor plugin. All device info fields are optional.
    - Call `/devices/redeem_link_device_code/` api and pass the following data:
        - `link_code`- link code taken from QR code
        - `verifying_pubkey` - pubkey creating using `xpubkey` and `nonce`
        - `device_id`, `name`, `device_model`, `os` - optional information about the POS app's device
    - `/devices/redeem_link_device_code/` api returns the pos device's info
    - After successfull call, the app stores `link_code`, `xpubkey`, `walle_hash`, `posid`
