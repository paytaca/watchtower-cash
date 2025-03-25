import { binToHex, encodeLockingBytecodeP2sh32, generateRandomBytes, hexToBin } from "@bitauth/libauth";
import { Contract } from "cashscript";

import { getBaseBytecode } from "./anyhedge.js";
import { TreasuryContract } from "../contracts/treasury-contract/index.js";
import { generateProxyFunderContractWithArtifact } from "../contracts/liquidity-provider/proxy-funder-gen.js";
import { AnyHedgeManager } from "@generalprotocols/anyhedge";


/**
 * @param {Object} opts 
 * @param {String} [opts.anyhedgeVersion]
 */
export function createTreasuryContract(opts) {
  const { bytecode } = getBaseBytecode({ version: opts?.anyhedgeVersion })
  const authKeyId = generateRandomBytes(32);
  const pubkeys = Array.from({ length: 5 }).map(() => generateRandomBytes(33))
  const contractParams = [authKeyId, ...pubkeys.map(hexToBin), bytecode]
  const artifact = TreasuryContract.getArtifact('v2')
  const contract = new Contract(artifact, contractParams, { addressType: 'p2sh32' })

  return {
    artifact,
    contract,
    authKeyId: binToHex(authKeyId),
    pubkeys,
  }
}


/**
 * @param {Object} opts 
 * @param {Number} opts.contributorNum
 * @param {String} [opts.anyhedgeVersion]
 */
export function createProxyFunder(opts) {
  const contributorNum = opts?.contributorNum;
  const artifact = generateProxyFunderContractWithArtifact(contributorNum)
  
  let sum = 100;
  const contributions = Array.from({ length: contributorNum }, (_, index) => {
    if (index + 1 == contributorNum) return sum
    return Math.max(Math.floor(Math.random() * sum), 1);
  }).map(BigInt);
  
  const contributors = contributions.map(() => encodeLockingBytecodeP2sh32(generateRandomBytes(32)))

  const { bytecode } = getBaseBytecode({ version: opts?.anyhedgeVersion })
  const constructorArgs = [...contributions, ...contributors, hexToBin(bytecode)]
  const contract = new Contract(artifact, constructorArgs, { addressType: 'p2sh32' })

  return {
    artifact,
    contract,
    contributions,
    contributors: contributors.map(binToHex),
  }
}


/**
 * @param {Object} opts
 * @param {String} opts.shortAddress
 * @param {String} opts.longAddress
 * @param {String} opts.shortPubkey
 * @param {String} opts.longPubkey
 * @param {Object} opts.priceData
 * @param {String} opts.priceData.pubkey
 * @param {String} opts.priceData.message
 * @param {String} opts.priceData.message_timestamp
 * @param {Number} opts.liquidityFeePctg
 */
export async function createAnyhedgeContract(opts) {
  const priceData = opts?.priceData ? opts?.priceData : {
    pubkey: '02d09db08af1ff4e8453919cc866a4be427d7bfe18f2c05e5444c196fcf6fd2818',
    message: '5221dd678f2410007724100030810000',
    signature: 'cf08429d880d1145ef1614eefc93015c0a9f640630b72f740f3eedf5f355b91711fc3d5502c6fdd5f19ca1da033fdff390ef554a6159de3b3d96099e71b1e586',
    message_timestamp: 1742545234,
  }

  const manager = new AnyHedgeManager()
  const contractData = await manager.createContract({
    makerSide: 'long',
    takerSide: 'short',
    nominalUnits: 100,
    oraclePublicKey: priceData?.pubkey,
    startingOracleMessage: priceData?.message,
    startingOracleSignature: priceData?.signature,
    shortMutualRedeemPublicKey: opts?.shortPubkey,
    longMutualRedeemPublicKey: opts?.longPubkey,
    shortPayoutAddress: opts?.shortAddress,
    longPayoutAddress: opts?.longAddress,
    maturityTimestamp: BigInt(priceData?.message_timestamp + 86_400),
    lowLiquidationPriceMultiplier: 0.5,
    highLiquidationPriceMultiplier: 5,
    enableMutualRedemption: 1n,
    isSimpleHedge: 0n,
  })

  if (opts?.liquidityFeePctg) {
    const liquidityFee = contractData.metadata.shortInputInSatoshis * BigInt(opts?.liquidityFeePctg) / 100n
    await manager.addContractFee(contractData, {
      address: opts?.longAddress,
      satoshis: liquidityFee,
      name: 'Liquidity fee',
      description: 'LP Fee for long position',
    })
  }
  return contractData
}
