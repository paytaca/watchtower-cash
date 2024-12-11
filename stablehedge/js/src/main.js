import fs from 'fs'
import funcs from './funcs/index.js'
import url from 'node:url';


if (import.meta.url.startsWith('file:')) {
    const modulePath = url.fileURLToPath(import.meta.url);
    if (process.argv[1] === modulePath) {
        const data = JSON.parse(fs.readFileSync(0, 'utf-8'))
        const response = await runScript(data)
        if (response.success) console.log(response.result)
        else console.error(response.error)
    }
}

/**
 * @param {Object} data 
 * @param {String} data.function
 * @param {any[]} [data.params]
 */
export async function runScript(data) {
    const func = funcs[data?.function]
    if (!func) return {
        success: false,
        result: undefined,
        error: `'${data?.function}' function not found`
    }

    try {
        const response = await func(...(data?.params || []))
        return { success: true, result: JSON.stringify(response), error: undefined }
    } catch(error) {
        let errorResponse 
        if (typeof error === 'string') errorResponse = error
        else if (typeof error?.stack === 'string') errorResponse = error.stack
        else if (typeof error?.message === 'string') errorResponse = error?.message
        else errorResponse = error
        return { success: false, result: undefined, error: errorResponse }
    }
}
