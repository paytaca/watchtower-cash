import { hexToBin } from "@bitauth/libauth";
import { SignatureTemplate } from "cashscript";

/**
 * @param {Object} data
 * @param {String} data.lockingBytecode
 * @param {String} data.unlockingBytecode
 * @returns {SignatureTemplate}
 */
export function templateFromUnlockingBytecode(data) {
  return {
    unlockP2PKH() {
      return {
        generateLockingBytecode: () => hexToBin(data?.lockingBytecode),
        generateUnlockingBytecode: () => hexToBin(data?.unlockingBytecode),
      }
    }
  }
}
