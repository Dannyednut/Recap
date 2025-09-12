# Smart Contracts for DEX Arbitrage

## FlashLoanArbitrage.sol

This contract enables flash loan arbitrage execution using Aave V3 as the flash loan provider. The contract automatically adapts to the network environment based on the ArbitrageWise centralized configuration system.

### Features

- **Cross-DEX Arbitrage**: Buy on one DEX, sell on another
- **Triangular Arbitrage**: Execute 3-hop trades within the same DEX  
- **Flash Loan Integration**: Uses Aave V3 for capital-free arbitrage
- **Multi-Chain Support**: Ethereum, BSC, and Polygon networks
- **Multi-DEX Support**: Uniswap V2/V3, SushiSwap, PancakeSwap, QuickSwap
- **Network-Aware Deployment**: Automatically uses correct addresses for mainnet/testnet
- **Safety Features**: Minimum profit checks, reentrancy protection

### Network Configuration

The contract deployment uses ArbitrageWise's centralized network configuration:

- **Mainnet Deployment** (`MAINNET=True`): Uses production DEX routers and token addresses
- **Testnet Deployment** (`MAINNET=False`): Uses testnet DEX routers and token addresses

### Deployment

```bash
# Install dependencies
npm install @aave/core-v3 @openzeppelin/contracts

# Compile with Hardhat/Foundry
npx hardhat compile

# Deploy using the Python script (respects MAINNET environment variable)
python deploy.py
```

### Usage

1. **Cross Arbitrage**:
```solidity
contract.executeCrossArbitrage(
    WETH_ADDRESS,      // asset to flash loan
    1 ether,           // amount
    UNISWAP_ROUTER,    // buy DEX
    SUSHISWAP_ROUTER,  // sell DEX  
    USDC_ADDRESS,      // intermediate token
    0.01 ether         // minimum profit
)
```

2. **Triangular Arbitrage**:
```solidity
contract.executeTriangularArbitrage(
    WETH_ADDRESS,      // start token
    USDC_ADDRESS,      // hop 1
    DAI_ADDRESS,       // hop 2  
    1 ether,           // amount
    UNISWAP_ROUTER,    // DEX router
    0.01 ether         // minimum profit
)
```

### Security Considerations

- Only owner can execute arbitrage
- Reentrancy protection enabled
- Emergency withdrawal functions
- Minimum profit validation

### Gas Optimization

- Efficient swap routing
- Minimal external calls
- Optimized for MEV execution