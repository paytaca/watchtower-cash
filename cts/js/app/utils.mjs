import { AuthGuard } from './Authguard.mjs'

export const getAuthGuardAddress = (tokenId, addressType) => {
  const network = process.env.CTS_APP_ENV === 'development' ? 'testnet': 'mainnet'
  const authguard = new AuthGuard(
      tokenId, 
      network
  )
  let addr = {}
  if (addressType === 'token-deposit-address') {
    addr = {
      [tokenId]: authguard.contract.getTokenDepositAddress(),
      network
    }
  } else {
    addr = {
      [tokenId]: authguard.contract.getDepositAddress(),
      network
    }
  }
  return addr
}