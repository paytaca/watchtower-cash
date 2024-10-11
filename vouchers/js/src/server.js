import express from 'express'
import bodyParser from 'body-parser'

import * as device from './funcs/vault/device.js'
import * as merchant from './funcs/vault/merchant.js'


const app = express()
app.use(bodyParser.json({ limit: '50mb' }))

const port = 3002
const root = {
  device: '/vouchers/vault/device',
  merchant: '/vouchers/vault/merchant',
}

// device vault

app.post(`${root.device}/release`, async (req, res) => {
  const result = await device.release(req.body)
  res.send(result)
})

app.post(`${root.device}/send-tokens`, async (req, res) => {
  const result = await device.sendTokens(req.body)
  res.send(result)
})

app.post(`${root.device}/emergency-refund`, async (req, res) => {
  const result = await device.emergencyRefund(req.body)
  res.send(result)
})

app.post(`${root.device}/compile`, async (req, res) => {
  const result = await device.compile(req.body)
  res.send(result)
})

// merchant vault

app.post(`${root.merchant}/compile`, async (req, res) => {
  const result = await merchant.compile(req.body)
  res.send(result)
})

app.post(`${root.merchant}/emergency-refund`, async (req, res) => {
  const result = await merchant.emergencyRefund(req.body)
  res.send(result)
})

app.post(`${root.merchant}/claim`, async (req, res) => {
  const result = await merchant.claim(req.body)
  res.send(result)
})

app.post(`${root.merchant}/refund`, async (req, res) => {
  const result = await merchant.refund(req.body)
  res.send(result)
})

// listener

app.listen(port, () => {
  console.log(`Vouchers app listening on port ${port}`)
})