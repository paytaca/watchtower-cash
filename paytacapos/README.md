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


# POS Device unlinking flow
Unlinking is initiated by the merchant then confirmed by the pos device
1. (Main app) Creates a unlink request through `/devices/{wallet_hash_posid}/unlink_device/`
    - The app will generate a random `nonce` and sign the linked device's `link_code` using the key pair of the wallet at index `nonce`
    - Pass the `nonce` & `signature` to api for creating an unlink request
2. (POS app) POS Device confirm unlink request
    - Device retrieves the device info which has the unlink request data needed to confirm
    - To verify that the pos device confirmed the unlink process, the device must generate the pubkey of the wallet at index `nonce`

- Both either side can cancel the unlink request through `/devices/{wallet_hash_posid}/unlink_device/cancel/`
