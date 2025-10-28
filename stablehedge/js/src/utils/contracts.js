import { binToHex } from "@bitauth/libauth";
import { asmToScript, generateRedeemScript, scriptToBytecode } from "@cashscript/utils";
import { encodeConstructorArguments } from "cashscript/dist/Argument.js";

/**
 * @param {import("cashscript").Artifact} artifact
 * @param {any[]} parameters
 */
export function encodeParameterBytecode(artifact, parameters) {
  const encodedArgs = encodeConstructorArguments(artifact, parameters).slice();
  const argsScript = generateRedeemScript(new Uint8Array(), encodedArgs);
  const bytecodesHex = argsScript.map(script => {
    return binToHex(scriptToBytecode([script]))
  })

  // Patch breaking change for upgrading cashscript version from 0.11.0-next.4 to 0.11.5
  // Added this .reverse() to keep original order of parameters as expected at the time this function was written
  bytecodesHex.reverse();

  return bytecodesHex
}

export function baseBytecodeToHex(bytecode) {
  const script = asmToScript(bytecode)
  const baseScript = generateRedeemScript(script, new Uint8Array())  
  const baseBytecode = scriptToBytecode(baseScript)
  return binToHex(baseBytecode)
}
