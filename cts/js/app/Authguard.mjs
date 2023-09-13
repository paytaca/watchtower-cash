import { Contract } from "@mainnet-cash/contract"

export class AuthGuard {

  constructor(tokenId, network) {
    this._contract = new Contract(
      this.contractScript,
      [`0x${tokenId.match(/[a-fA-F0-9]{2}/g)?.reverse().join('')}`],
      network
    )
  }

  get contract() {
    return this._contract
  }

  get contractScript() {
    return `
    pragma cashscript ^0.8.0;

    contract AuthGuard(bytes tokenId) {
      function unlockWithNft(bool keepGuarded) {
        // Check that the first input holds the minting baton
        require(tx.inputs[1].tokenCategory == tokenId);
        require(tx.inputs[1].tokenAmount == 0);
        if(keepGuarded){
          // Self preservation of the minting covenant as the first output
          require(tx.outputs[0].lockingBytecode == tx.inputs[this.activeInputIndex].lockingBytecode);
        }
      }
    }`
  }
}
