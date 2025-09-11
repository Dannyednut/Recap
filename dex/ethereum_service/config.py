import os
from typing import List, Dict

class EthereumConfig:
    # Network Configuration
    CHAIN_ID = int(os.getenv("ETH_CHAIN_ID", "1"))  # 1=mainnet, 11155111=sepolia
    RPC_URL = os.getenv("ETH_RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY")
    WSS_URL = os.getenv("ETH_WSS_URL", "wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY")
    
    # Wallet Configuration
    PRIVATE_KEY = os.getenv("ETH_PRIVATE_KEY", "")
    WALLET_ADDRESS = os.getenv("ETH_WALLET_ADDRESS", "")
    
    # Gas Configuration
    MAX_GAS_PRICE_GWEI = int(os.getenv("ETH_MAX_GAS_PRICE_GWEI", "50"))
    GAS_PRICE_MULTIPLIER = float(os.getenv("ETH_GAS_PRICE_MULTIPLIER", "1.1"))
    
    # Trading Configuration
    MIN_PROFIT_THRESHOLD = float(os.getenv("ETH_MIN_PROFIT_THRESHOLD", "0.5"))  # %
    MAX_SLIPPAGE = float(os.getenv("ETH_MAX_SLIPPAGE", "0.5"))  # %
    MAX_TRADE_SIZE_ETH = float(os.getenv("ETH_MAX_TRADE_SIZE", "10.0"))
    
    # DEX Addresses
    UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
    UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    UNISWAP_V3_ROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"  # SwapRouter02 with multicall
    UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    UNISWAP_V3_QUOTER_V2 = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
    
    SUSHISWAP_ROUTER = "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
    SUSHISWAP_FACTORY = "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac"
    
    # Flash Loan Providers
    AAVE_LENDING_POOL = "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9"
    DYDX_SOLO_MARGIN = "0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e"
    
    # Common Tokens (Mainnet addresses)
    TOKENS = {
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48",  # Correct USDC mainnet address
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
    }
    
    # Mempool Configuration
    MEMPOOL_MONITOR_ENABLED = os.getenv("ETH_MEMPOOL_MONITOR", "False") == "True"
    MIN_MEV_OPPORTUNITY_USD = float(os.getenv("ETH_MIN_MEV_OPPORTUNITY", "100.0"))
    
    @classmethod
    def validate(cls):
        errors = []
        if not cls.RPC_URL or "YOUR_KEY" in cls.RPC_URL:
            errors.append("ETH_RPC_URL not properly configured")
        if not cls.PRIVATE_KEY:
            errors.append("ETH_PRIVATE_KEY not set")
        if errors:
            raise RuntimeError(f"Ethereum config validation errors: {'; '.join(errors)}")