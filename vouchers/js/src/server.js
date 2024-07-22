import { claimVoucher } from './funcs/vault'
import express from 'express'

const app = express()
const port = 3002


app.post('/claim', async (req, res) => {
  const result = await claimVoucher(req.body)
  res.send(result)
})

app.listen(port, () => {
  console.log(`Vouchers app listening on port ${port}`)
})

