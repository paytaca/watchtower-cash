import { AnyHedgeManager } from "@generalprotocols/anyhedge";

/**
 *
 * @param {Object} settlementService 
 * @param {String} settlementService.scheme 
 * @param {String} settlementService.domain 
 * @param {String} settlementService.port 
 */
export async function getSettlementServiceAuthToken(settlementService) {
  const manager = new AnyHedgeManager({
    serviceScheme: settlementService.scheme,
    serviceDomain: settlementService.domain,
    servicePort: settlementService.port,
  })
  return await manager.requestAuthenticationToken('Paytaca')
}
