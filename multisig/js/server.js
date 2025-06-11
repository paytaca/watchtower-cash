import structuredClone from '@ungap/structured-clone'

import express from 'express'
import {
    decodeCashAddress,
    encodeCashAddress,
    CashAddressType,
    CashAddressNetworkPrefix,
    importWalletTemplate,
    walletTemplateToCompilerBCH,
    lockingBytecodeToCashAddress,
    binToHex,
    hexToBin,
    cashAddressToLockingBytecode,
    hashTransaction,
    decodeTransactionCommon,
    stringify
} from 'bitauth-libauth-v3'
import * as Multisig from './multisig/index.js'

if (typeof global.structuredClone === 'undefined') {
  global.structuredClone = structuredClone;
}
const app = express()
const port = 3004

app.use(express.json());

app.use(express.urlencoded({ extended: true }));

app.post('/multisig/utils/derive-wallet-address', async (req, res) => {
    const { template, lockingData } = req.body
    const { cashAddressNetworkPrefix } = req.query
    const validTemplate = importWalletTemplate(template);
    const compiler = walletTemplateToCompilerBCH(validTemplate);
    const lockingBytecode = compiler.generateBytecode({
        data: lockingData,
        scriptId: lockingScript,
        debug: true
      })

    const cashAddress = lockingBytecodeToCashAddress({
        bytecode: lockingBytecode.bytecode,
        prefix: cashAddressNetworkPrefix || CashAddressNetworkPrefix.mainnet
    })
    const tokenAddress = lockingBytecodeToCashAddress({
        bytecode: lockingBytecode.bytecode,
        prefix: cashAddressNetworkPrefix || CashAddressNetworkPrefix.mainnet,
        tokenSupport: true
    })

    res.send({
        cashAddress: cashAddress.address,
        tokenAddress: tokenAddress.address,
        payload: binToHex(cashAddress.payload)
    })
})

app.post('/multisig/utils/get-transaction-hash', async (req, res) => {
  // transaction hex
  const { transaction } = req.body
  const decoded = decodeTransactionCommon(hexToBin(transaction))
  res.send({ transaction_hash: hashTransaction(decoded) })
})

app.post('/multisig/transaction/finalize', async (req, res) => {
   const { multisigTransaction, multisigWallet } =  req.body
   const multisigTransactionImported = Multisig.importPst({ pst: multisigTransaction })
   const finalCompilation = Multisig.finalizeTransaction({ multisigTransaction: multisigTransactionImported, multisigWallet })
      
   res.json({ finalCompilation: stringify(finalCompilation)})
})

app.get('/test', async (req, res) => {
   res.send({hello: 'hello test'})
})

app.listen(port, () => {
    console.log(`Multisig express server listening on port ${port}`)
})
