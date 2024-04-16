import fs from 'fs'
import { exit } from 'process'
import funcs from './funcs/index.js'

const data = JSON.parse(fs.readFileSync(0, 'utf-8'))
const func = funcs[data.function]
if (!func) {
    console.error(`'${data.function}' function not found`)
    exit(1)
}

try {
    const response = await func(...(data.params || []))
    console.log(JSON.stringify(response, (_, value) => typeof value === 'bigint' ? value.toString() : value))
} catch(error) {
    if (typeof error === 'string') console.error(error)
    else if (typeof error?.stack === 'string') console.error(error.stack)
    else if (typeof error?.message === 'string') console.error(error?.message)
    else console.error(error)
    exit(1)
}
