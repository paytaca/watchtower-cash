#!/usr/bin/env node
/**
 * Example Node.js client for listening to JPP invoice payment updates via WebSocket.
 *
 * Usage:
 *     node websocket_client_example.js <invoice_uuid> [host]
 *
 * Example:
 *     node websocket_client_example.js 1234567890abcdef1234567890abcdef
 *     node websocket_client_example.js 1234567890abcdef1234567890abcdef watchtower.cash
 *
 * Requirements:
 *     npm install ws
 */

const WebSocket = require('ws');

function main() {
    const args = process.argv.slice(2);
    
    if (args.length < 1) {
        console.log('Usage: node websocket_client_example.js <invoice_uuid> [host]');
        console.log('Example: node websocket_client_example.js 1234567890abcdef1234567890abcdef');
        console.log('Example: node websocket_client_example.js 1234567890abcdef1234567890abcdef watchtower.cash');
        process.exit(1);
    }
    
    const invoiceUuid = args[0];
    const host = args[1] || 'localhost:8000';
    const protocol = host.includes('watchtower.cash') ? 'wss' : 'ws';
    
    const wsUrl = `${protocol}://${host}/ws/jpp/invoice/${invoiceUuid}/`;
    
    console.log(`Connecting to: ${wsUrl}`);
    
    const ws = new WebSocket(wsUrl);
    
    ws.on('open', function() {
        console.log('WebSocket connection established');
        console.log('Listening for payment updates...');
    });
    
    ws.on('message', function(data) {
        const message = JSON.parse(data.toString());
        
        console.log('='.repeat(60));
        console.log('PAYMENT UPDATE RECEIVED!');
        console.log('='.repeat(60));
        console.log(`Type: ${message.type}`);
        console.log(`Transaction ID: ${message.txid}`);
        console.log(`Paid At: ${message.paid_at}`);
        
        if (message.memo) {
            console.log(`Memo: ${message.memo}`);
        }
        
        if (message.invoice) {
            console.log('\nInvoice Details:');
            console.log(`  Payment ID: ${message.invoice.payment_id}`);
            console.log(`  Network: ${message.invoice.network}`);
            console.log(`  Currency: ${message.invoice.currency}`);
            
            if (message.invoice.payment) {
                console.log(`  Total BCH: ${message.invoice.payment.total_bch || 'N/A'}`);
            }
        }
        
        console.log('='.repeat(60));
    });
    
    ws.on('error', function(error) {
        console.error(`WebSocket error: ${error.message}`);
    });
    
    ws.on('close', function(code, reason) {
        console.log(`WebSocket connection closed (code: ${code}, reason: ${reason.toString()})`);
    });
}

main();

