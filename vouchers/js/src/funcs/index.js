import {
  toBytes20,
  pubkeyToCashAddress
} from './utils.js'

import {
  compileVaultContract,
  emergencyRefund,
  claimVoucher,
} from './vault.js'


const funcs = {
  toBytes20,
  compileVaultContract,
  pubkeyToCashAddress,
  emergencyRefund,
  claimVoucher,
}

export default funcs
