import { ElectrumCluster, ElectrumTransport, ClusterOrder } from 'electrum-cash';

export default class ElectrumCashProvider {
  /**
   * @param {Object} opts 
   * @param {bool} opts.manualConnectionManagement
   * @param {'mainnet' | 'chipnet'} opts.network 
   */
  constructor(opts) {
    this.manualConnectionManagement = opts?.manualConnectionManagement
    switch(opts?.network) {
      case('chipnet'):
        this.network = 'chipnet'
        break;
      default:
        this.network = 'mainnet'
    }

    if (this.network == 'mainnet') {
      this.electrum = new ElectrumCluster('CashScript Application', '1.4.1', 2, 3, ClusterOrder.PRIORITY);
      this.electrum.addServer('bch.imaginary.cash', 50004, ElectrumTransport.WSS.Scheme, false);
      this.electrum.addServer('blackie.c3-soft.com', 50004, ElectrumTransport.WSS.Scheme, false);
      this.electrum.addServer('electroncash.de', 60002, ElectrumTransport.WSS.Scheme, false);
      this.electrum.addServer('electroncash.dk', 50004, ElectrumTransport.WSS.Scheme, false);
      this.electrum.addServer('bch.loping.net', 50004, ElectrumTransport.WSS.Scheme, false);
      this.electrum.addServer('electrum.imaginary.cash', 50004, ElectrumTransport.WSS.Scheme, false);
    } else if(this.network == 'chipnet') {
      this.electrum = new ElectrumCluster('CashScript Application', '1.4.1', 1, 1, ClusterOrder.PRIORITY);
      this.electrum.addServer('chipnet.imaginary.cash', 50004, ElectrumTransport.WSS.Scheme, false);
    }

    this.concurrentRequests = 0
  }

  async connectCluster() {
    try {
      return await this.electrum.startup();
    }
    catch (e) {
      return [];
    }
  }
  async disconnectCluster() {
    return this.electrum.shutdown();
  }

  shouldConnect() {
    if (this.manualConnectionManagement)
      return false;
    if (this.concurrentRequests !== 0)
      return false;
    return true;
  }
  shouldDisconnect() {
    if (this.manualConnectionManagement)
      return false;
    if (this.concurrentRequests !== 1)
      return false;
    return true;
  }

  async performRequest(name, ...parameters) {
    // Only connect the cluster when no concurrent requests are running
    if (this.shouldConnect()) {
      this.connectCluster();
    }
    this.concurrentRequests += 1;
    await this.electrum.ready();
    let result;
    try {
      result = await this.electrum.request(name, ...parameters);
    }
    finally {
      // Always disconnect the cluster, also if the request fails
      // as long as no other concurrent requests are running
      if (this.shouldDisconnect()) {
        await this.disconnectCluster();
      }
    }
    this.concurrentRequests -= 1;
    if (result instanceof Error)
      throw result;
    return result;
  }
}
