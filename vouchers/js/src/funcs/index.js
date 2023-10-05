import { compileVaultContract, emergencyRefund } from './vault.js'
import { toBytes20, pubkeyToCashAddress } from './utils.js'


const funcs = {
  toBytes20,
  compileVaultContract,
  pubkeyToCashAddress,
  emergencyRefund,
}

export default funcs
