const fs = require('fs');
const CryptoJS = require('crypto-js');

(async () => {
    await calculateSHA256('rampp2p/escrow/src/escrow.cash')
})();

async function calculateSHA256(filePath) {
    const fileData = await readFile(filePath)
    const hash = CryptoJS.SHA256(fileData);
    console.log(`{"contract_hash": "${hash.toString()}"}`)
}

function readFile(filePath) {
    return new Promise((resolve, reject) => {
      fs.readFile(filePath, (error, fileData) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(fileData);
      });
    });
  }
