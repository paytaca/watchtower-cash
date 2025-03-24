import * as fs from 'fs';
import * as url from 'url';
import { compileString } from "cashc";
import { asmToScript, generateRedeemScript, scriptToBytecode } from "@cashscript/utils";
import { binToHex } from '@bitauth/libauth';

/**
 * @param {Number} numContributors 
 * @returns 
 */
export function generateProxyFunderContract(numContributors) {
    if (numContributors < 1) {
        throw new Error("At least one contributor is required.");
    }

    const contributions = Array.from({ length: numContributors }, (_, i) => i)

    // Generate contributor parameters
    const contributorPctgParams = contributions
        .map((pctg, i) => `    int contribution${i + 1}Pctg`)
        .join(",\n");
    const contributorLockScriptParams = contributions
        .map((pctg, i) => `    bytes35 contributor${i + 1}`)
        .join(",\n");

    // Generate output validation checks
    const payoutChecks = contributions
        .map((pctg, i, list) => 
        `        require(val / contribution${i + 1}Pctg == tx.outputs[${i}].value);`
        )
        .join("\n");

    const payoutAddressChecks = contributions.map((pctg, i) => 
        `        require(tx.outputs[${i}].lockingBytecode == contributor${i + 1});`
        )
        .join("\n");

    // 510 => base fee (this would be the single input)
    // 45 * n => fee for each output (not yet sure of the value) 
    const fees = 510 + 45 * numContributors;

    return `pragma cashscript ^0.8.0;

contract ProxyFunder${numContributors}(
${contributorPctgParams},
${contributorLockScriptParams},
    bytes anyhedgeBaseBytecode
) {
    function payout() {
        require(tx.inputs.length == 1);
        require(tx.outputs.length == ${numContributors});

        // fee = 510 base sats + 45 * numContributors
        int val = (tx.inputs[0].value - ${fees}) * 100;
${payoutChecks}

${payoutAddressChecks}
    }

    function spendToContract(bytes argsSegment1, bytes argsSegment2) {
        bytes35 thisLockScript = new LockingBytecodeP2SH32(hash256(this.activeBytecode));
        bytes contractParametersBytecode = argsSegment2 +
            bytes(35) + thisLockScript +
            argsSegment1;

        bytes contractBytecode = contractParametersBytecode + anyhedgeBaseBytecode;
        bytes35 anyhedgeLockscript = new LockingBytecodeP2SH32(hash256(contractBytecode));
        require(tx.outputs[0].lockingBytecode == anyhedgeLockscript);
    }
}`;
}


export function generateProxyFunderContractWithArtifact(num) {
  const code = generateProxyFunderContract(num);
  return compileString(code);
}

function baseBytecodeChecks(baseBytecode = '') {
  const split = (str='', index) => [str.substring(0, index), str.substring(index)];
  const segment1 = baseBytecode.slice(baseBytecode.startsWith('01') ? 4 : 2);
  const [commonSegment1, segment2] = split(segment1, 16);

  const segment1Check = '79009c63c3519dc4' == commonSegment1;

  const [commonSegment2, segment3] = split(segment2.slice(2), 8);
  const segment2Check = '9d00c602' == commonSegment2

  const commonSegment3 = segment3.slice(4, 12);
  const segment3Check = '94016495' === commonSegment3

  return {
    segment1Check,
    segment2Check,
    segment3Check,
  }
}

function bytecodeToHex(bytecode) {
  const script = asmToScript(bytecode)
  const baseScript = generateRedeemScript(script, new Uint8Array())  
  const baseBytecode = scriptToBytecode(baseScript)
  return binToHex(baseBytecode)
}


const modulePath = url.fileURLToPath(import.meta.url);
if (process.argv[1] === modulePath) {
  const displayHelp = process.argv.indexOf('-h')
  const nContribsIndex = process.argv.indexOf('-n')
  const nContributions = nContribsIndex >= 0 ? parseInt(process.argv[nContribsIndex+1]) : 4

  const checkBaseBytecode = process.argv.indexOf('-c') >= 0
  const saveArgIndex = process.argv.indexOf('--save')

  if (displayHelp >= 0) {
    console.log('-c', 'Check bytecode if segments still match validation in lp.cash')
    console.log('--save', ['source', 'abi', 'artifact'], 'Save to a file.')
    console.log('-n', 'Set number of contributors. Defaults to 4')
    process.exit();
  }
  console.log('Creating proxy funder with', nContributions, 'contributors')
  const result = generateProxyFunderContractWithArtifact(nContributions);

  if (saveArgIndex >= 0) {
    const saveType = process.argv[saveArgIndex+1]

    let path, data
    if (saveType == 'source') {
      const filename = `proxy-funder-${nContributions}.cash`;
      path = `./${filename}`
      data = result.source
    } else if (saveType == 'abi' || saveType == 'artifact') {
      const filename = `proxy-funder-${nContributions}.artifact.json`;
      path = `./${filename}`
      data = JSON.stringify(result, undefined, 2)
    } else {
      throw new Error('Unsupported save type')
    }
    fs.writeFile(
      path, data,
      (err) => {
        if (err) throw err
      }
    )
  } else {
    console.log(result)
  }

  if (checkBaseBytecode) {
    const bytecode = bytecodeToHex(result.bytecode)
    const bytecodeChecksResult = baseBytecodeChecks(bytecode)
    console.log(bytecodeChecksResult)
  }
}

