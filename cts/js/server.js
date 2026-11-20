#!/usr/bin/env node

import express from 'express'
import serviceAuth from '../../internal_services/auth.cjs'
import { getAuthGuardAddress } from './app/utils.mjs'

const app = express()
app.use(serviceAuth.serviceAuthMiddleware('CTS_JS_AUTH_TOKEN'))

const PORT = process.env.PORT || 3001

app.get('/cts/js/authguard-deposit-address/:tokenId', (req, res) => {
  res.json(getAuthGuardAddress(req.params.tokenId, '')) 
})

app.get('/cts/js/authguard-token-deposit-address/:tokenId', (req, res) => {
  res.json(getAuthGuardAddress(req.params.tokenId, 'token-deposit-address'))
})

app.listen(PORT, '127.0.0.1', () => {
  console.log(`CTS listening on port ${PORT}`)
})
