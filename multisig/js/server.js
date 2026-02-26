import structuredClone from '@ungap/structured-clone'

import express from 'express'
import {
    CashAddressNetworkPrefix,
    importWalletTemplate,
    walletTemplateToCompilerBCH,
    lockingBytecodeToCashAddress,
    binToHex,
    hexToBin,
    decodeHdPublicKey,
    deriveHdPathRelative,
    hashTransaction,
    stringify,
    secp256k1,
    sha256,
    utf8ToBin,
    decodeTransactionCommon
} from 'bitauth-libauth-v3'
import * as Multisig from './multisig/index.js'
import { Pst, combine as combinePsts } from './multisig/pst.js'
import { ElectrumClient } from '@electrum-cash/network'
import { MultisigTransactionBuilder } from './multisig/index.js'

if (typeof global.structuredClone === 'undefined') {
  global.structuredClone = structuredClone;
}
const app = express()
const port = 3004
app.use(express.json());

app.use(express.urlencoded({ extended: true }));

app.get('/multisig/wallet/utxos', async (req, res) => {

   const util = await import('util')
   const address = req.query.address
   const filter  = 'include_tokens' 


   let network = 'mainnet'
   let hostname = 'electrum.imaginary.cash'
   let utxos = []
 
   if (address) {

     if (address.startsWith('bchtest')) {
        network = 'chipnet'
        hostname = 'chipnet.bch.ninja'
     }
     const client = new ElectrumClient('Watchtower', '1.4.1', hostname)
     try {
      await client.connect()
      utxos = await client.request('blockchain.address.listunspent', address, filter) 
     } catch(e) {
       console.log(e)
     } finally {
       client.disconnect()
     }
   }

   utxos = utxos.map((utxo) => {
     const watchtowerUtxo = {
        txid: utxo.tx_hash,
	vout: utxo.tx_pos,
	value: utxo.value,
	height: utxo.height
     }
     if (utxo.token_data) {
       watchtowerUtxo.token = {
          amount: utxo.token_data.amount,
	  category: utxo.token_data.category
       }
       if (utxo.token_data.nft) {
         watchtowerUtxo.token.nft = {
           capability: utxo.token_data.nft.capability,
	   commitment: utxo.token_data.nft.commitment
	 }
       }
     }
     return watchtowerUtxo
   })
   res.send(utxos)
})

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
  res.send({ transaction_hash: hashTransaction(hexToBin(transaction)) })
})

app.post('/multisig/transaction/finalize', async (req, res) => {
   const { multisigTransaction, multisigWallet } =  req.body
   const multisigTransactionImported = Multisig.importPst({ pst: multisigTransaction })
   const finalCompilation = Multisig.finalizeTransaction({ multisigTransaction: multisigTransactionImported, multisigWallet })      
   res.send(JSON.parse(stringify(finalCompilation)))
})

app.post('/multisig/transaction/get-signing-progress', async (req, res) => {
   const { multisigTransaction, multisigWallet } =  req.body
   const multisigTransactionImported = Multisig.importPst({ pst: multisigTransaction })
   const signingProgress = Multisig.getSigningProgress({ multisigWallet, multisigTransaction })
   res.send({ signingProgress })
})

app.post('/multisig/message/verify-signature', async (req, res) => {
  const { message, publicKey, signature } = req.body
  const messageHash = sha256.hash(utf8ToBin(message))
  let success = false
  try {
    if (signature.schnorr) {
      success = secp256k1.verifySignatureSchnorr(
        hexToBin(signature.schnorr), hexToBin(publicKey), messageHash
      )
    }
    if (signature.der) {
      success = secp256k1.verifySignatureDER(
        hexToBin(signature.der), hexToBin(publicKey), messageHash
      )
    }  
  } catch (error) {
    console.log(error)
    return res.send({ success: false, error: error })
  }
  
  return res.send({ success })
})

app.post('/multisig/transaction/decode-psbt', async (req, res) => {
  const { psbt } = req.body
  const decoded = Pst.fromPsbt(psbt)
  res.send({...decoded.toJSON(), signingProgress: decoded.getSigningProgress()})
})

app.post('/multisig/transaction/decode-proposal', async (req, res) => {
  if (req.body.proposal_format !== 'psbt') {
    return res.send({ error: 'Only psbt proposals are supported' })
  }
  const { proposal } = req.body
  const decoded = Pst.fromPsbt(proposal)
  const decodedProposal = {
    unsigned_transaction_hex: decoded.unsignedTransactionHex,
    unsigned_transaction_hash: decoded.unsignedTransactionHash, 
    proposal_format: 'psbt',
    proposal,
    inputs: []
  }
  const decodedTransaction = decodeTransactionCommon(hexToBin(decoded.unsignedTransactionHex))
  for (const input of decodedTransaction.inputs) {
    decodedProposal.inputs.push({
      outpoint_transaction_hash: binToHex(input.outpointTransactionHash),
      outpoint_index: input.outpointIndex,
    })
  }
  res.send(decodedProposal)
})

app.post('/multisig/transaction/combine-psbts', async (req, res) => {
  const { psbts } = req.body
  try {
    const decodedPsbts = psbts.map(psbt => Pst.import(psbt))
    const combined = await combinePsts(decodedPsbts)
    res.send({
      result: await combined.export('psbt')
    })    
  } catch (error) {
    console.error('Error combining PSBTs:', error)
    return res.status(400).send({ error: 'Failed to combine PSBTs: ' + error.message })
  }
  
})

app.get('/multisig/transaction/unsigned-transaction-hash', async (req, res) => {
  const decodedTransaction = decodeTransactionCommon(hexToBin(req.query.transaction_hex))
  decodedTransaction.inputs[0].unlockingBytecode = []
  const transactionBuilder = new MultisigTransactionBuilder()
  transactionBuilder.setVersion(decodedTransaction.version)
  transactionBuilder.setLocktime(decodedTransaction.locktime)
  transactionBuilder.addInputs(decodedTransaction.inputs.map(i => {
    return {
      ...i,
      unlockingBytecode: new Uint8Array([])
    }
  }))
  transactionBuilder.addOutputs(decodedTransaction.outputs)
  res.send({
    unsigned_transaction_hash: hashTransaction(hexToBin(transactionBuilder.build()))
  })
})






app.listen(port, () => {
    console.log(`Multisig express server listening on port ${port}`)
})
