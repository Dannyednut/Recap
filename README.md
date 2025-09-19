# ArbitrageWise: Multi-Chain DEX Arbitrage System

ArbitrageWise is a comprehensive arbitrage system that monitors and executes profitable trading opportunities across multiple blockchains and decentralized exchanges (DEXs).

## 🚀 Features

- **Multi-Chain Support**: Ethereum, BSC, Polygon, and Solana
- **Centralized Network Configuration**: Single `MAINNET` variable controls all blockchain networks
- **Multiple Arbitrage Strategies**:
  - Cross-Exchange Arbitrage
  - Triangular Arbitrage
  - Mempool Backrun Arbitrage (MEV)
- **Flashloan Integration**: Aave V2/V3, Balancer, dYdX
- **Production-Ready DEX Integrations**:
  - **Ethereum**: Uniswap V2/V3, SushiSwap
  - **BSC**: PancakeSwap V2/V3, Biswap, ApeSwap
  - **Polygon**: QuickSwap, SushiSwap, Uniswap V3, Curve
  - **Solana**: Raydium, Orca, Jupiter aggregator
- **Real-time Price Aggregation**: Cross-chain price comparison and opportunity detection
- **Dynamic Token Discovery**: Automatic discovery of new tokens and trading pairs
- **Web API**: RESTful API for monitoring and executing trades
- **Comprehensive Testing**: Unit tests and integration tests for all components

## 🏗️ Architecture

The system is built with a modular and microservice architecture that allows for easy extension and maintenance:

### Core Components

- **ArbitrageManager**: Coordinates multi-chain arbitrage operations
- **ChainFactory**: Creates chain-specific components
- **NetworkConfig**: Centralized network configuration system
- **BaseEngine**: Abstract blockchain interaction layer
- **BaseArbitrageStrategy**: Template for arbitrage strategies

### Centralized Configuration System

- **NetworkConfig** (`dex/shared/network_config.py`): Single source of truth for all network configurations
- **MAINNET Environment Variable**: Controls mainnet/testnet switching across all chains
- **Automatic Address Management**: Token and DEX contract addresses switch based on network
- **Chain-Specific Configs**: Ethereum, BSC, Polygon configurations use centralized system

### Chain-Specific Components

For each supported blockchain (Ethereum, BSC, Polygon, Solana):

- **Engine**: Chain-specific blockchain interaction with real RPC calls
- **Config**: Network configuration that inherits from centralized NetworkConfig
- **TokenDiscoveryService**: Discovers and tracks trading pairs
- **FlashloanEngine**: Manages flashloan providers and execution
- **ContractExecutor**: Handles smart contract interactions with real DEX contracts
- **ArbitragePipeline**: Coordinates strategy execution across multiple engines
- **MempoolMonitor**: Monitors pending transactions for MEV opportunities

### Shared Utilities

- **Logger** (`dex/shared/logger.py`): Centralized logging system
- **Utils** (`dex/shared/utils.py`): Contract ABI loading, formatting, validation
- **Models**: Shared data models for arbitrage opportunities and execution results

### Smart Contracts

- **ArbitrageExecutor.sol**: Main contract for executing arbitrage trades

## Setup

### Prerequisites

- Python 3.8+
- Web3.py
- Quart (async Flask)
- Solidity compiler (for smart contracts)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ArbitrageWise-Refined.git
cd ArbitrageWise-Refined

# Install dependencies
pip install -r requirements.txt

# Compile smart contracts
cd contracts
npx hardhat compile
```

### Configuration

1. **Copy the environment template:**
```bash
cp .env.example .env
```

2. **Configure the MAINNET variable:**
```bash
# For production mainnet deployment
MAINNET=True

# For testnet development and testing
MAINNET=False
```

3. **Set your API keys and private keys:**
```bash
# RPC Endpoints
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BSC_RPC_URL=https://bsc-dataseed1.binance.org/
POLYGON_RPC_URL=https://polygon-rpc.com/
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Private Keys (NEVER commit these to version control)
ETH_PRIVATE_KEY=your-ethereum-private-key
BSC_PRIVATE_KEY=your-bsc-private-key
POLYGON_PRIVATE_KEY=your-polygon-private-key
SOLANA_PRIVATE_KEY=your-solana-private-key

# API Keys
INFURA_API_KEY=your-infura-api-key
ALCHEMY_API_KEY=your-alchemy-api-key
ETHERSCAN_API_KEY=your-etherscan-api-key
BSCSCAN_API_KEY=your-bscscan-api-key
POLYGONSCAN_API_KEY=your-polygonscan-api-key
JUPITER_API_KEY=your-jupiter-api-key

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id
```

**Important Notes:**
- The `MAINNET` variable automatically configures all blockchain networks
- When `MAINNET=True`: Uses mainnet chains (Ethereum=1, BSC=56, Polygon=137)
- When `MAINNET=False`: Uses testnets (Sepolia=11155111, BSC Testnet=97, Mumbai=80001)
- All DEX addresses and token contracts are managed automatically based on the MAINNET setting

## Usage

### Starting the System

```bash
python main.py
```

### API Endpoints

- `GET /`: Health check
- `GET /balances`: Get CEX and DEX balances
- `GET /dex/status`: Get DEX service status
- `GET /dex/opportunities`: Get current arbitrage opportunities
- `POST /dex/execute`: Execute an arbitrage opportunity
- `GET /dex/chains`: Get supported and active chains
- `GET /dex/chain/<chain_id>`: Get status of a specific chain
- `GET /system/status`: Get comprehensive system status

### Running Tests

```bash
# Run all tests
python tests/run_tests.py

# Run specific test modules
python tests/run_tests.py -m test_arbitrage_strategies test_mempool_monitor

# Test network configuration switching
python test_network_config.py
```

### Deployment

1. **For Production (Mainnet):**
```bash
export MAINNET=True
python main.py
```

2. **For Development (Testnet):**
```bash
export MAINNET=False
python main.py
```

The system will automatically use the correct network configurations, token addresses, and DEX contract addresses based on the MAINNET setting.

## 🏛️ Architecture Diagram

```
                    ┌─────────────────────────────────────┐
                    │         MAINNET Environment         │
                    │         Variable Control            │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │      NetworkConfig (Centralized)    │
                    │   • Chain IDs & RPC URLs           │
                    │   • Token Addresses                 │
                    │   • DEX Contract Addresses          │
                    └─────────────────┬───────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Ethereum       │         │      BSC        │         │    Polygon      │
│  Service        │         │    Service      │         │    Service      │
│                 │         │                 │         │                 │
│ ┌─────────────┐ │         │ ┌─────────────┐ │         │ ┌─────────────┐ │
│ │   Config    │ │         │ │   Config    │ │         │ │   Config    │ │
│ │ (inherits)  │ │         │ │ (inherits)  │ │         │ │ (inherits)  │ │
│ └─────────────┘ │         │ └─────────────┘ │         │ └─────────────┘ │
│ ┌─────────────┐ │         │ ┌─────────────┐ │         │ ┌─────────────┐ │
│ │   Engine    │ │         │ │   Engine    │ │         │ │   Engine    │ │
│ └─────────────┘ │         │ └─────────────┘ │         │ └─────────────┘ │
│ ┌─────────────┐ │         │ ┌─────────────┐ │         │ ┌─────────────┐ │
│ │ Arbitrage   │ │         │ │ Arbitrage   │ │         │ │ Arbitrage   │ │
│ │ Pipeline    │ │         │ │ Pipeline    │ │         │ │ Pipeline    │ │
│ └─────────────┘ │         │ └─────────────┘ │         │ └─────────────┘ │
└─────────────────┘         └─────────────────┘         └─────────────────┘
        │                             │                             │
        └─────────────────────────────┼─────────────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │        ArbitrageManager             │
                    │     (Multi-Chain Coordinator)       │
                    └─────────────────────────────────────┘

Shared Components:
┌─────────────────────────────────────────────────────────────────────────┐
│  dex/shared/                                                            │
│  ├── logger.py          (Centralized logging)                          │
│  ├── utils.py           (Contract ABI, formatting, validation)         │
│  ├── network_config.py  (Network configuration management)             │
│  └── models/            (Shared data models)                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.