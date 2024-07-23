import express from 'express'
import bodyParser from 'body-parser'
import {
  claimVoucher,
  compileVaultContract,
  emergencyRefund,
  refundVoucher,
} from './funcs/vault.js'


const app = express()
app.use(bodyParser.json({ limit: '50mb' }))

const port = 3002
const root = '/vouchers'


app.post(`${root}/claim`, async (req, res) => {
  const result = await claimVoucher(req.body)
  res.send(result)
})

app.post(`${root}/refund`, async (req, res) => {
  const result = await refundVoucher(req.body)
  res.send(result)
})

app.post(`${root}/emergency-refund`, async (req, res) => {
  const result = await emergencyRefund(req.body)
  res.send(result)
})

app.post(`${root}/compile-vault`, async (req, res) => {
  const result = await compileVaultContract(req.body)
  res.send(result)
})

app.listen(port, () => {
  console.log(`Vouchers app listening on port ${port}`)
})