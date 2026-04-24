from hdwallet import HDWallet
from hdwallet.cryptocurrencies import BitcoinCash
from hdwallet.derivations import CustomDerivation
from hdwallet.hds import BIP32HD
from hdwallet.addresses.bitcoincash import BitcoinCashAddress

def hdwallet_from_xpub(xpub: str):
    hd = HDWallet(BitcoinCash, hd=BIP32HD)
    hd.from_xpublic_key(xpub, strict=False)
    return hd

def is_account_xpub(xpub: str, hdwallet: HDWallet = None):
    hd = hdwallet or hdwallet_from_xpub(xpub)
    return hd.depth() == 3 and hd.index() >= 2147483648

def is_receive_xpub(xpub: str, hdwallet: HDWallet = None):
    hd = hdwallet or hdwallet_from_xpub(xpub)
    return hd.depth() == 4 and hd.index() == 0

def is_change_xpub(xpub: str, hdwallet: HDWallet = None):
    hd = hdwallet or hdwallet_from_xpub(xpub)
    return hd.depth() == 4 and hd.index() == 1

def is_defi_xpub(xpub: str, hdwallet: HDWallet = None):
    hd = hdwallet or hdwallet_from_xpub(xpub)
    return hd.depth() == 4 and hd.index() == 7

def derive_address_from_xpub(xpub: str, index: int, hdwallet:HDWallet = None):
    hd = hdwallet or hdwallet_from_xpub(xpub)
    address = {
        'index': index
    }
    if is_account_xpub(xpub, hdwallet=hd):
        address['receive'] = hd.from_derivation(derivation=CustomDerivation(path=f"m/0/{index}")).address(BitcoinCashAddress)
        address['change'] = hd.from_derivation(derivation=CustomDerivation(path=f"m/1/{index}")).address(BitcoinCashAddress)
        address['defi'] = hd.from_derivation(derivation=CustomDerivation(path=f"m/7/{index}")).address(BitcoinCashAddress)
    if is_receive_xpub(xpub, hdwallet=hd):
        address['receive'] = hd.from_derivation(derivation=CustomDerivation(path=f"m/{index}")).address(BitcoinCashAddress)
    if is_change_xpub(xpub, hdwallet=hd):
        address['change'] = hd.from_derivation(derivation=CustomDerivation(path=f"m/{index}")).address(BitcoinCashAddress)
    if is_defi_xpub(xpub, hdwallet=hd):
        address['defi']  = hd.from_derivation(derivation=CustomDerivation(path=f"m/{index}")).address(BitcoinCashAddress)
    
    return address

def is_valid_address(address: str):
    try:
        BitcoinCashAddress.decode(address)
        return True 
    except ValueError as e:
        print(e)
        return False
