# WatchTower.Cash

**Instant and reliable infrastructure connecting you to the Bitcoin Cash blockchain**

WatchTower.Cash is a comprehensive blockchain infrastructure service that provides real-time monitoring, notifications, and advanced financial tools for the Bitcoin Cash ecosystem. Built for reliability at scale with 99.99% uptime guarantees.

## 🚀 Core Features

### Blockchain Infrastructure
- **Real-time UTXO database** for subscribed addresses
- **Instant notifications** via webhooks and WebSockets
- **Transaction broadcasting** and mempool monitoring
- **HD wallet tracking** and address subscription management
- **Multiple node support** with failover capabilities

### Advanced Wallet Solutions
- **Multisig wallet management** with support for 2-of-3, 2-of-4, and custom m-of-n configurations
- **Wallet templates** following LibAuth standards
- **Transaction proposal workflow** with multi-signer coordination
- **Secure authentication** using public key cryptography

### DeFi & Derivatives
- **Anyhedge derivatives trading** - create and manage hedge contracts with oracle price feeds
- **Stablehedge treasury management** - automated shorting and rebalancing of treasury contracts
- **Oracle price feeds** with real-time market data
- **Contract settlement services** with automated execution

### Trading & Exchange
- **P2P exchange platform** with escrow contracts and arbitration system
- **Real-time order matching** and market price feeds
- **Escrow smart contracts** for secure peer-to-peer trading
- **Arbitration system** for dispute resolution
- **Cash-in services** with preset payment methods

### Smart Contract Support
- **Contract event parsing** and subscription management
- **Block parsing** with configurable batch sizes

### Payment & Merchant Tools
- **JSON Payment Protocol (BIP70)** support for merchant payments
- **Invoice management** and payment verification
- **Merchant POS integration** for business payment processing
- **Payment request handling** with transaction validation

### Communication & Notifications
- **Push notification system** with Firebase integration
- **WebSocket APIs** for real-time updates across all services
- **Telegram bot integration** for alerts and updates
- **Email notifications** for important events

### Business Solutions
- **Gift card and voucher system** for promotional campaigns
- **Merchant cash-out services** for business operations
- **Feature control system** for app management
- **Multi-tenant support** with country-specific features

## 🏗️ Architecture

### Reliability Features
- **Distributed parallel background task queue** for block scanning and notifications
- **Multiple failover nodes/indexers** as data sources
- **Resource optimization** - watches only subscribed addresses
- **Scalable infrastructure** designed for enterprise use

### Technology Stack
- **Backend**: Django with PostgreSQL and Redis
- **Real-time**: Django Channels with WebSocket support
- **Task Queue**: Celery with Redis backend
- **Blockchain**: Direct node connections (BCHN, BCHD, Fulcrum)
- **Smart Contracts**: CashScript and Anyhedge integration

## 📚 Documentation & Libraries

- [**API Documentation & Browser**](https://watchtower.cash/api/docs/)
- [**JavaScript/Node.js Package**](https://github.com/paytaca/watchtower-cash-js)
- [**Python Package**](https://github.com/paytaca/watchtower-cash-py)
- [**Swagger UI**](https://watchtower.cash/api/docs/)
- [**ReDoc**](https://watchtower.cash/api/redoc/)

## 🔌 API Endpoints

### Core Services
- `/api/` - Main blockchain APIs (addresses, transactions, subscriptions)
- `/api/anyhedge/` - Derivatives and hedge contract management
- `/api/stablehedge/` - Treasury contract services
- `/api/multisig/` - Multisig wallet operations
- `/api/ramp-p2p/` - P2P exchange platform
- `/api/paytacapos/` - Merchant POS integration
- `/api/notifications/` - Push notification services
- `/api/jpp/` - JSON Payment Protocol implementation

### WebSocket Channels
- `/ws/anyhedge/updates/{wallet_hash}/` - Anyhedge contract updates
- `/ws/ramp-p2p/subscribe/` - P2P exchange real-time updates
- `/ws/watch_room/` - General blockchain monitoring

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- PostgreSQL 11+
- Redis 6+
- Node.js 16+ (for JavaScript tooling)

### Quick Start
```bash
# Clone the repository
git clone https://github.com/paytaca/watchtower-cash.git
cd watchtower-cash

# Install dependencies
pip install -r requirements.txt
npm install

# Configure environment
cp .env.example .env
# Edit .env with your configuration

# Run migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

### Docker Deployment
```bash
# Using docker-compose
docker-compose -f compose/mainnet.yml up -d

# Or for chipnet testing
docker-compose -f compose/chipnet.yml up -d
```

## 🔧 Configuration

### Environment Variables
- `BCH_NETWORK` - Network selection (mainnet/chipnet)
- `START_BLOCK` - Starting block for blockchain scanning
- `REDIS_HOST`, `REDIS_PORT` - Redis connection settings
- `BCHN_HOST`, `BCHD_HOST` - Bitcoin Cash node connections

### Feature Toggles
- Enable/disable specific app features via admin panel
- Country-specific feature restrictions
- App version compatibility checks

## 📊 Monitoring & Analytics

- **Real-time block scanning** with configurable intervals
- **Transaction validation** and mempool monitoring
- **Price feed aggregation** from multiple sources
- **Performance metrics** and health checks
- **Error tracking** and logging

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines and development setup instructions.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Telegram**: [@WatchTowerCash](https://t.me/WatchTowerCash)
- **Documentation**: [https://watchtower.cash/api/docs/](https://watchtower.cash/api/docs/)
- **Issues**: [GitHub Issues](https://github.com/paytaca/watchtower-cash/issues)

---

**Built with ❤️ by the Paytaca team for the Bitcoin Cash community**
