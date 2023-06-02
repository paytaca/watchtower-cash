
const TOKEN_ID = process.argv[2]

const BCHJS = require('@psf/bch-js')
const bchjs = new BCHJS()

const run = async () => {
  try {
    let tokenData = await bchjs.PsfSlpIndexer.getTokenData(TOKEN_ID)
    console.log(JSON.stringify(tokenData))
  } catch(error) {
    console.error(error)
  }
}

run()
