import fs from 'fs'
import funcs from './funcs/index.js'

const data = JSON.parse(fs.readFileSync(0, 'utf-8'))
const func = funcs[data.function]
if (!func) throw new Error(`'${data.function}' function not found`)

const response = await func(...(data.params || []))
console.log(JSON.stringify(response))
