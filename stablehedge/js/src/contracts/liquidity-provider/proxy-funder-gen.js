import * as fs from 'fs';
import * as url from 'url';
import path from 'path'
import { compileString } from 'cashc';
import { baseBytecodeToHex } from '../../utils/contracts.js';

/**
 * @param {Number} numContributors 
 * @returns 
 */
export function generateProxyFunderContract(numContributors) {
  const contributions = Array.from({ length: numContributors }, (_, i) => i)

  const contributorPctgParams = contributions
    .map((_, i) => `int contributor${i + 1}BasisPts`)

  const contributorLockScriptParams = contributions
    .map((_, i) => `bytes35 contributor${i + 1}`)


  const contributionsList = contributions
    .map((_, i) => {
      return `    int contributor${i+1}BasisPts = int(contributions.split(${i*2})[1].split(2)[0]);`
    })

  const payoutChecks = contributions
    .map((_, i, list) => 
    `        require((val * contributor${i+1}BasisPts) / 10000 == tx.outputs[0].value);`
    )

  const payoutAddressChecks = contributions.map((pctg, i) => 
    `        require(tx.outputs[${i}].lockingBytecode == contributor${i + 1});`
    )

  const fees = 510 + 45 * numContributors;

  const replace = [
    ['contract ProxyFunder',          `contract ProxyFunder${numContributors}`],
    // [contributorPctgParams[0],        contributorPctgParams.join(', ')],
    [contributorLockScriptParams[0],  contributorLockScriptParams.join(', ')],
    [/int fee = \d+;/,                `int fee = ${fees};`],
    [contributionsList[0],            contributionsList.join('\n')],
    [payoutChecks[0],                 payoutChecks.join('\n')],
    [payoutAddressChecks[0],          payoutAddressChecks.join('\n')],
  ]

  let sourceCode = getBaseSourceCode()
  replace.forEach(data => {
    const [search, replace] = data
    if (search instanceof RegExp) {
      if (!search.test(sourceCode)) throw new Error(`Unable to find pattern to replace: ${search}`)
    } else if (!sourceCode.includes(search)) {
      throw new Error(`Unable to find substring to replace:\n'${search}'`)
    }

    sourceCode = sourceCode.replace(search, replace)
  })
  return sourceCode
}

export function generateProxyFunderContractWithArtifact(num) {
  const code = generateProxyFunderContract(num);
  try {
    return compileString(code);
  } catch(error) {
    console.log(code)
    throw error
  }
}

function getBaseSourceCode() {
  let filePath = new URL(import.meta.url).pathname
  const dirname = path.dirname(filePath)
  const src = fs.readFileSync(path.resolve(dirname, 'proxy-funder-base.cash'), 'utf8')
  return src
}

function baseBytecodeChecks(baseBytecode = '') {
  const split = (str='', index) => [str.substring(0, index), str.substring(index)];
  const segment1 = baseBytecode.slice(baseBytecode.startsWith('01') ? 4 : 2);
  const [commonSegment1, segment2] = split(segment1, 24);

  const segment1Check = '79009c63c352a169c4519d02' == commonSegment1;

  const [commonSegment2, segment3] = split(segment2.slice(4), 40);
  const segment2Check = '00c67c94c3529c6301647851c69378947b757768' == commonSegment2

  const commonSegment3 = segment3.slice(2, 16);
  const segment3Check = '007f77527f7581' === commonSegment3

  return {
    segment1Check,
    segment2Check,
    segment3Check,
  }
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
    const bytecode = baseBytecodeToHex(result.bytecode)
    console.log('bytecode', bytecode)
    const bytecodeChecksResult = baseBytecodeChecks(bytecode)
    console.log(bytecodeChecksResult)
  }
}

