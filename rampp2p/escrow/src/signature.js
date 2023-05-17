const { ec: EC } = require('elliptic');

(async () => {
    const public_key_hex = process.argv[2]
    const der_signature_hex = process.argv[3]
    const message = process.argv[4]
    verifySignature(public_key_hex, der_signature_hex, message)
})();

function verifySignature(publicKeyHex, derSignatureHex, message){
    const ec = new EC('secp256k1');

    // Load the public key from the hex representation
    const publicKey = ec.keyFromPublic(publicKeyHex, 'hex');
  
    // Verify the DER-encoded signature
    const isVerified = publicKey.verify(message, derSignatureHex, 'hex');
    console.log(`{"is_verified": ${isVerified}}`)
}