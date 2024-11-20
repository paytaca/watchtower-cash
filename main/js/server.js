import express from 'express'
import {
    decodeCashAddress,
    encodeCashAddress,
    CashAddressType,
    CashAddressNetworkPrefix,
} from '@bitauth/libauth'
import { Wallet as MainnetWallet, TestNetWallet } from 'mainnet-js';
import ElectrumCashProvider from './utils/electrum-cash-provider.js'



function validateAddress(address, isTokenAddress=false) {
    const result = { valid: false }
    try {
        const decodedAddress = decodeCashAddress(address)
        let validTypes = [
            CashAddressType.p2pkh,
            CashAddressType.p2sh,
        ]
        
        if (isTokenAddress) {
            validTypes = [
                CashAddressType.p2pkhWithTokens,
                CashAddressType.p2shWithTokens,
            ]
        }
    
        result.valid = validTypes.includes(decodedAddress.type)
    } catch {}
    return result
}


function bchAddressConverter (address, toTokenAddress) {
    const isTestnet = address.split(':')[0].indexOf('test') >= 0
    const prefix = isTestnet ? CashAddressNetworkPrefix.testnet : CashAddressNetworkPrefix.mainnet
    const decodedAddr = decodeCashAddress(address)
    let type = CashAddressType.p2pkh

    let resultAddress = address
    if (toTokenAddress) {
        switch (decodedAddr.type) {
            case CashAddressType.p2pkh:
                type = CashAddressType.p2pkhWithTokens;
                break
            case CashAddressType.p2sh:
                type = CashAddressType.p2shWithTokens;
                break
            case CashAddressType.p2pkhWithTokens:
                return resultAddress
            case CashAddressType.p2shWithTokens:
                return resultAddress
        }
    } else {
        switch (decodedAddr.type) {
            case CashAddressType.p2pkh:
                return resultAddress
            case CashAddressType.p2sh:
                return resultAddress
            case CashAddressType.p2pkhWithTokens:
                type = CashAddressType.p2pkh
                break
            case CashAddressType.p2shWithTokens:
                type = CashAddressType.p2sh
                break
        }
    }

    resultAddress = encodeCashAddress(prefix, type, decodedAddr.payload)
    return resultAddress
}

function getTransactions(address, network=''){
    const provider = new ElectrumCashProvider({ network })
    return provider.performRequest('blockchain.address.get_history', address)
        .catch(error => {
            console.error(error)
            return []
        })
}


const app = express()
const port = 3000

app.get('/validate-address/:address', (req, res) => {
    const isTokenAddress = req.query.token === 'True'
    const result = validateAddress(req.params.address, isTokenAddress)
    res.send(result)
})

app.get('/convert-address/:address', (req, res) => {
    const toTokenAddress = req.query.to_token === 'True'
    const resultAddress = bchAddressConverter(req.params.address, toTokenAddress)
    res.send(resultAddress)
})

app.get('/get-transactions/:address', async (req, res) => {
    const network = req.query.network
    const response = await getTransactions(req.params.address, network)
    res.send(response)
})

app.post('/verify-signature', async (req, res) => {
    try {
      let Wallet = MainnetWallet
      if (req.body.bch_address.startsWith('bchtest')) {
        Wallet = TestNetWallet
      }
      let wallet = await Wallet.watchOnly(req.body.bch_address)
      const verifyResult = await wallet.verify(req.body.message, req.body.signature)  
      res.send(verifyResult)
    } catch (error) {
      console.log('@jsserver /verify-signature: ', error)
      res.send(error)
    }
  })

app.listen(port, () => {
    console.log(`Example app listening on port ${port}`)
})
