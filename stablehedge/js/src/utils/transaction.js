import { SignatureTemplate } from "cashscript"
import { placeholder, scriptToBytecode } from "@cashscript/utils"
import { createInputScript, getInputSize, getPreimageSize } from "cashscript/dist/utils.js";

/**
 * Taken directly from Transaction class' fee calculation
 * Returns the bytesize of contract's transaction input
 * @param {Transaction} transaction
 */
export function calculateInputSize(transaction) {
  const placeholderArgs = transaction.args.map((arg) => (arg instanceof SignatureTemplate ? placeholder(65) : arg));
  // Create a placeholder preimage of the correct size
  const placeholderPreimage = transaction.abiFunction.covenant
      ? placeholder(getPreimageSize(scriptToBytecode(transaction.contract.redeemScript)))
      : undefined;
  // Create a placeholder input script for size calculation using the placeholder
  // arguments and correctly sized placeholder preimage
  const placeholderScript = createInputScript(transaction.contract.redeemScript, placeholderArgs, transaction.selector, placeholderPreimage);
  // Add one extra byte per input to over-estimate tx-in count
  const contractInputSize = getInputSize(placeholderScript) + 1;
  return contractInputSize
}
