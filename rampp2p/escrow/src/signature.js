const { ec: EC } = require('elliptic');
const { padTo32Bytes } = require('elliptic').utils;
const ACTION = process.argv[2]

(async () => {
    if (ACTION == 'verify') {
        const public_key_hex = process.argv[3]
        const der_signature_hex = process.argv[4]
        const message = process.argv[5]
        verifySignature(public_key_hex, der_signature_hex, message)
    }

    if (ACTION == 'decode-sig') {
        const der_signature_hex = process.argv[3]
        convertDERtoSignature(der_signature_hex)
    }

})();

function convertDERtoSignature(derSignature) {
    const ec = new EC('secp256k1');
    const signature = ec.signatureFromDER(derSignature, 'hex');
    sig = {
      r: padTo32Bytes(signature.r),
      s: padTo32Bytes(signature.s),
      recoveryParam: signature.recoveryParam
    }
    console.log(`{"signature": "${sig}"}`)
}

function verifySignature(publicKeyHex, derSignatureHex, message){

    try {
        const ec = new EC('secp256k1');

        // Load the public key from the hex representation
        const publicKey = ec.keyFromPublic(publicKeyHex, 'hex');
    
        // Verify the DER-encoded signature
        const isVerified = publicKey.verify(message, derSignatureHex, 'hex');
        console.log(`{"is_verified": ${isVerified}}`)

    } catch (error) {
        console.log(`{"is_verified": false, "error": "${error}"}`)
    }
}