import { CashAddressNetworkPrefix, decodeCashAddress } from "bitauth-libauth-v3";
import { ElectrumNetworkProvider } from 'cashscript';

/**
 * @typedef {'mainnet' | 'testnet3' | 'testnet4' | 'chipnet' | 'mocknet' | 'regtest'} Network
 */

/**
 * @typedef {Object} NetworkProvider
 * @property {GetAddressUtxos}
 * @property {GetAddressBalance}
 * @property {GetWalletUtxos}
 * @property {GetWalletBalance}
 * @property {GetWalletHashUtxos}
 * @property {GetWalletHashBalance}
 * @property {string} hostname
 * 
 */

/**
 * @typedef {Object} NetworkProviderOptions
 * @property {string}
 * @property {GetAddressBalance}
 * @property {GetWalletUtxos}
 * @property {GetWalletBalance}
 * @property {GetWalletHashUtxos}
 * @property {GetWalletHashBalance}
 * @property {Network} network
 * @property {string} hostname
 */

/**
 * @typedef {Object} WatchtowerMultisigCoordinationServerAuthCredentials
 * @property {string} "X-Auth-PubKey" - Hex-encoded public key used to sign the authentication message.
 * @property {string} "X-Auth-Signature" - Combined signature string in the format:
 *   "schnorr=<hex>;der=<hex>".
 * @property {string} "X-Auth-Message" - The raw message that was signed, typically provided by the server.
 */



/**
 * @type {{ [key in Network]: Network }}
 */
export const Network = {
  MAINNET: 'mainnet',
  TESTNET3: 'testnet3',
  TESTNET4: 'testnet4',
  CHIPNET: 'chipnet',
  MOCKNET: 'mocknet',
  REGTEST: 'regtest',
};

/**
 * @typedef {'mainnet' | 'chipnet'} WatchtowerNetworkType
 */

/**
 * @type {{ mainnet: WatchtowerNetworkType, chipnet: WatchtowerNetworkType }}
 */
export const WatchtowerNetwork = {
    mainnet: 'mainnet',
    chipnet: 'chipnet',
    local: 'local'
}
/**
 * @implements { NetworkProvider }
 */
export class WatchtowerNetworkProvider {

    /**
     * @param {Object} config
     * @param {WatchtowerNetworkType} config.network
     */
    constructor(config) {
        this.hostname = 'https://watchtower.cash'
        // this.hostname = 'http://localhost:8000'
        this.cashAddressNetworkPrefix = CashAddressNetworkPrefix.mainnet
        this.network = config?.network || WatchtowerNetwork.mainnet
        if (this.network === WatchtowerNetwork.chipnet) {
            this.hostname = 'https://chipnet.watchtower.cash'
            this.cashAddressNetworkPrefix = CashAddressNetworkPrefix.testnet
        }
    }

    // {
    //     txid: 'b9784ef85ef3f57039de7b56db40b70de96ddaa87a143be875e405a093163793',
    //     vout: 0,
    //     satoshis: 7200,
    //     height: 909242,
    //     coinbase: false,
    //     token: null,
    //     addressPath: '1/1',
    //     address: 'bitcoincash:pq7tl7yy4uy4nsvpmvgnmz2v5yhpmv5qg5degh2usg'
    // }
    // {
    //     "txid": "54f8d06f9f3120ceadc3f2ef88dda47604b830d0b62ecc724866941e288fac1c",
    //     "vout": 0,
    //     "satoshis": 1000,
    //     "height": 0,
    //     "coinbase": false,
    //     "token": {
    //      "amount": "30",
    //      "category": "ea9e1baca02a8f3cc266348d39bacc141bf885d76c0eacb0687c7ecd81ab86b5"
    //     }
    // }
    async getAddressUtxos(address, addressPath) {
        const data = await fetch(`${this.hostname}/api/multisig/wallets/utxos/${address}`).then(r => r.json())
        data?.forEach(utxo => {
            utxo.addressPath = addressPath
            utxo.address = address
            return utxo
        })
        return data || []
    }

    async getWalletHashUtxos(walletHash, utxoType = 'bch', tokenFilter = 'ft') {
        let url = `${this.hostname}/api/utxo/wallet/${walletHash}?is_cashtoken=${utxoType === 'cashtoken' ? 'true': 'false'}`
        if (utxoType === 'cashtoken' && tokenFilter === 'ft') {
            url += `&is_cashtoken_nft=false`
        }
        if (utxoType === 'cashtoken' && tokenFilter === 'nft') {
            url += `&is_cashtoken_nft=true`
        }
        return await fetch(url).then(r => r.json())

    }

    async getWalletUtxos(address) {
        throw new Error('Not yet implemented')
    }

    async getAddressBalance(address) {
        const decodedCashAddress = decodeCashAddress(address)
        return []
    }

    async getWalletHashBalance(multisigWalletHash) {
        throw new Error('Not yet implemented')
    }

    async getWalletBalance(multisigWallet) {
        throw new Error('Not yet implemented')
    }

    /**
     * @returns {Promise<{ success: boolean, txid: string }>}
     */
    async broadcastTransaction(rawTxHex) { 
        return await fetch(`${this.hostname}/api/broadcast/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transaction: rawTxHex })
        }).then(r => r.json())
    }

    async getRawTransaction(txid) {
        const provider = new ElectrumNetworkProvider(this.network)  
        return await provider.getRawTransaction(txid)
    }

    async getWalletTransactionHistory ({ walletHash, type = 'all', all='false',  tokenCategory='', page = 1 }) {
        
        let url = `${this.hostname}/api/history/wallet/${walletHash}`
        
        if (tokenCategory) {
          url += `/${tokenCategory}`
        }
      
        url += `?type=${type}&all=${all}&page=${page}`
        
        return await fetch(url).then(r => r.json())
      }
      

    async subscribeWalletAddressIndex ({ walletHash, addresses, addressIndex, type = 'pair' }) {
      
        if (type === 'pair') {
            addresses.receiving = receiveAddress
            addresses.change = changeAddress
        }

        if (type === 'deposit') {
            delete addresses.change 
        }
        
        if (type === 'change') {
            delete addresses.receiving
        }
        
        const projectId = {
            mainnet: process.env.WATCHTOWER_PROJECT_ID,
            chipnet: process.env.WATCHTOWER_CHIP_PROJECT_ID
        }

        return await fetch(`${this.hostname}/api/subscription/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_id: projectId[this.network],
                addresses,
                address_index: addressIndex,
                wallet_hash: walletHash
            })
        }).then(r => r.json()) 
    }
      
}

export class WatchtowerCoordinationServer {

    /**
     * @param {Object} config
     * @param {WatchtowerNetworkType} config.network
     */
    constructor(config) {
        this.network = config.network || WatchtowerNetwork.mainnet
        switch (this.network) {
            case WatchtowerNetwork.chipnet:
                // this.hostname = 'https://chipnet.watchtower.cash'
                // this.hostname = 'http://localhost:8000'
                this.hostname = 'http://192.168.1.41:8000'
                break
            case WatchtowerNetwork.mainnet:
                // this.hostname = 'https://watchtower.cash'    
                // this.hostname = 'http://localhost:8000'
                this.hostname = 'http://192.168.1.41:8000'
                break
            case WatchtowerNetwork.local:
                // this.hostname = 'http://localhost:8000'
                this.hostname = 'http://192.168.1.41:8000'
                break
        }
    }

    /**
     * @param {import('./wallet').MultisigWallet} wallet
     * @return {Promise<import('./wallet').MultisigWallet>}
     */
    async createWallet(wallet) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...await wallet.generateAuthCredentials() },
                body: JSON.stringify(wallet)
            }
        )
        return response.json()   
    }

    /**
     * @param {import('./wallet').MultisigWallet} wallet
     * @return {Promise<import('./wallet').MultisigWallet>} 
     */
    async uploadWallet({ wallet, authCredentialsGenerator }) {
        if (!authCredentialsGenerator) return null
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...await authCredentialsGenerator.generateAuthCredentials() },
                body: JSON.stringify(wallet)
            }
        )
        return response.json()   
    } 

    async updateWalletLastIssuedDepositAddressIndex(wallet, lastIssuedDepositAddressIndex, network) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${wallet.walletHash}/last-issued-deposit-address-index`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...await wallet.generateAuthCredentials() },
                body: JSON.stringify({ network: network || this.network, lastIssuedDepositAddressIndex })
            }
        )
        return response.json()
    }

    async updateWalletLastUsedDepositAddressIndex(wallet, lastUsedDepositAddressIndex, network) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${wallet.walletHash}/last-used-deposit-address-index`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...await wallet.generateAuthCredentials() },
                body: JSON.stringify({ network: network || this.network, lastUsedDepositAddressIndex })
            }
        )
        return response.json()
    }

    async updateWalletLastUsedChangeAddressIndex(wallet, lastUsedChangeAddressIndex, network) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${wallet.walletHash}/last-used-change-address-index`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...await wallet.generateAuthCredentials() },
                body: JSON.stringify({ network: network || this.network, lastUsedChangeAddressIndex })
            }
        )
        return response.json()
    }

    
    
    async uploadPst(pst) {
        const response = await fetch(
            `${this.hostname}/api/multisig/psts/`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...await pst.wallet.generateAuthCredentials() },
                body: JSON.stringify(pst)
            }
        )
        return response.json()
    }
     
    // --

    async createServerIdentity({ serverIdentity, authCredentialsGenerator }) {
        const authCredentials = await authCredentialsGenerator.generateAuthCredentials()
        
        if (!authCredentials) return null
        const response = await fetch(
            `${this.hostname}/api/multisig/coordinator/server-identities/`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authCredentials },
                body: JSON.stringify(serverIdentity)
            }
        )
        return response.json()
    }

    async getServerIdentity({ publicKey, authCredentialsGenerator }) {
        const authCredentials = await authCredentialsGenerator.generateAuthCredentials()
        const response = await fetch(
            `${this.hostname}/api/multisig/coordinator/server-identities/${publicKey}/`,
            { headers: { ...authCredentials } }
        )
        return response.json()
    }

    async getWallet({ identifier }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${identifier}/`
        )
        return response.json()
    }

    async getSignerWallets({ publicKey }) {        
        const response = await fetch(
            `${this.hostname}/api/multisig/signers/${publicKey}/wallets/`
        )
        return response.json()
    }


    async getSignerWalletsByMasterFingerprint({ masterFingerprint }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/signers/${masterFingerprint}/wallets/`
        )
        return response.json()
    }

    /**
     * @typedef {Object} Proposal
     * @property {string} [wallet] - The wallet id associated with the proposal.
     * @property {string} [proposal] - The serialized/encoded proposal.
     * @property {string} [proposalFormat] - Example: 'psbt' | 'libauth-template' only 'psbt' is supported now.
     * @param {Object} params
     * @param {Proposal} params.proposal - The proposal to upload.
     * @param {*} params.authCredentialsGenerator
     */
    async uploadProposal({ payload, authCosignerAuthCredentials, authCredentials }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authCredentials, ...authCosignerAuthCredentials },
                body: JSON.stringify(payload)
            }
        )
        return response.json()
    }

    /**
     * @typedef {Object} Proposal
     * @property {string} [wallet] - The wallet id associated with the proposal.
     * @property {string} [proposal] - The serialized/encoded proposal.
     * @property {string} [proposalFormat] - Example: 'psbt' | 'libauth-template' only 'psbt' is supported now.
     * @param {Object} params
     * @param {Proposal} params.proposal - The proposal to upload.
     * @param {*} [params.authCosignerCredentials] - Cosigner auth credentials 
     * @param {*} [params.authCredentialsGenerator] - 
     */
    async deleteProposal({ id, walletId, authCosignerCredentials, authCredentialsGenerator }) {
        let credentials = authCosignerCredentials
        if (!authCosignerCredentials && authCredentialsGenerator) {
            credentials = await authCredentialsGenerator.generateCosignerAuthCredentials()    
        }
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${id}/?wallet_id=${walletId}`, 
            { method: 'DELETE', headers: { ...credentials } }
        )
        return response.json()
    }

    async getProposalStatus({ unsignedTransactionHash, queryFilter }) {
        let url = `${this.hostname}/api/multisig/proposals/${unsignedTransactionHash}/status/`

        if (queryFilter?.includeDeleted) {
            url += '?include_deleted=true'
        }
        const response = await fetch(url)
        return response?.json()
    }

    async getProposalByUnsignedTransactionHash(unsignedTransactionHash) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${unsignedTransactionHash}/`
        )
        return response.json()
    }

    async getProposalCoordinator({ unsignedTransactionHash }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${unsignedTransactionHash}/coordinator/`
        )
        return response?.json()
    }

    /**
     * Fetches the list of decoded signer signature data for a proposal and signer.
     *
     * @param {Object} params
     * @param {string} params.masterFingerprint - The signer's master fingerprint.
     * @param {string} params.proposalUnsignedTransactionHash - The unsigned transaction hash for the proposal.
     * @returns {Promise<import('./pst.js').DecodedSignerSignatureData[]>} Array of decoded signature data relevant to the provided master fingerprint.
     */
    async getSignerSignatures({ masterFingerprint, proposalUnsignedTransactionHash }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${proposalUnsignedTransactionHash}/signatures/${masterFingerprint}/`
        )
        return response.json()
    }

    async getSignatures({ proposalUnsignedTransactionHash }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${proposalUnsignedTransactionHash}/signatures/`
        )
        return response.json()
    }

    async getPsbts({ proposalUnsignedTransactionHash }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${proposalUnsignedTransactionHash}/psbts/`
        )
        return response.json()
    }

    /**
     * Submits a partial signature for a multisig proposal.
     *
     * @param {Object} params
     * @param {string} params.proposalUnsignedTransactionHash - The unsigned transaction hash for the proposal.
     * @param {string} params.content - The partial signature payload; could be a PSBT base64 string or some other format. Currently only supports PSBT.
     * @param {string} [params.standard='psbt'] - The standard serialization format of the payload, default is 'psbt'.
     * @param {string} params.authCredentialsGenerator - Object or class instance that knows how to generate cosigner credential for this particular proposal.
     * @returns {Promise<Object>} Response data from the signature submission.
     */
    async submitPsbt({ content, standard = 'psbt', encoding = 'base64', proposalUnsignedTransactionHash, walletId, authCosignerAuthCredentials }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/proposals/${proposalUnsignedTransactionHash}/psbts/?wallet_id=${walletId}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authCosignerAuthCredentials },
                body: JSON.stringify({ content, standard, encoding })
            }
        )

        return response?.json()
    }

     /**
      * Fetches proposals for a wallet.
      *
      * @param {string} walletIdentifier - Identifier for the wallet; can be a wallet id, walletHash, or walletDescriptorId.
      * @returns {Promise<Array<{ 
      *   id: number, 
      *   wallet: number, 
      *   proposal: string, 
      *   proposalFormat: string, 
      *   unsignedTransactionHex: string 
      * }>>} Array of proposals associated with the given wallet.
      */
    async getWalletProposals(walletIdentifier, status='pending') {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${walletIdentifier}/proposals/?status=${status}`
        )
        return response.json()
    }

    async uploadWalletWcSession({ walletIdentifier, payload, authCosignerAuthCredentials }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${walletIdentifier}/walletconnect/sessions/`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authCosignerAuthCredentials },
                body: JSON.stringify(payload)
            }
        )
        return response.json()
    }

    async getWalletWcSessions({ walletIdentifier }) {
        const response = await fetch(
            `${this.hostname}/api/multisig/wallets/${walletIdentifier}/walletconnect/sessions/`,
        )
        return response.json()
    }
}