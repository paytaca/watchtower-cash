import express from 'express'
import {
  claimVoucher,
  compileVaultContract,
  emergencyRefund,
  refundVoucher,
} from './funcs/vault'


const app = express()
const port = 3002


app.post('/claim', async (req, res) => {
  const result = await claimVoucher(req.body)
  res.send(result)
})

app.post('/refund', async (req, res) => {
  const result = await refundVoucher(req.body)
  res.send(result)
})

app.post('/emergency-refund', async (req, res) => {
  const result = await emergencyRefund(req.body)
  res.send(result)
})

app.post('/compile-vault', async (req, res) => {
  const result = await compileVaultContract(req.body)
  res.send(result)
})

app.listen(port, () => {
  console.log(`Vouchers app listening on port ${port}`)
})

