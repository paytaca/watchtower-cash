import BCHJS from '@psf/bch-js';
const bchjs = new BCHJS({
    restURL: 'https://bchn.fullstack.cash/v5/',
    apiToken: process.env.BCHJS_TOKEN
});

(async () => {
    try {
      let current = await bchjs.Price.rates();
      const response = {
        "rates": current
      }
      console.log(JSON.stringify(response));
    } catch(err) {
      console.error(JSON.stringify(err))
    }
})()