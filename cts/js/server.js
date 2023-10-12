#!/usr/bin/env node

import express from 'express'
import { getAuthGuardAddress } from './app/utils.mjs'

const app = express()

const PORT = process.env.PORT || 3001

app.get('/cts/js/authguard-deposit-address/:tokenId', (req, res) => {
  res.json(getAuthGuardAddress(req.params.tokenId, '')) 
})

app.get('/cts/js/authguard-token-deposit-address/:tokenId', (req, res) => {
  res.json(getAuthGuardAddress(req.params.tokenId, 'token-deposit-address'))
})

app.listen(PORT, () => {
  console.log(`CTS listening on port ${PORT}`)
})
