import os
from typing import List, Dict

class PolygonConfig:
    # Network Configuration
    CHAIN_ID = int(os.getenv("POLYGON_CHAIN_ID", "137"))  # 137=mainnet, 80001=mumbai testnet
    RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com/")
    WSS_URL = os.getenv("POLYGON_WSS_URL", "wss://polygon-rpc.com/")
    
    # Wallet Configuration
    PRIVATE_KEY = os.getenv("POLYGON_PRIVATE_KEY", "")
    WALLET_ADDRESS = os.getenv("POLYGON_WALLET_ADDRESS", "")
    
    # Gas Configuration (Polygon uses EIP-1559)
    MAX_FEE_PER_GAS_GWEI = int(os.getenv("POLYGON_MAX_FEE_PER_GAS_GWEI", "100"))
    MAX_PRIORITY_FEE_PER_GAS_GWEI = int(os.getenv("POLYGON_MAX_PRIORITY_FEE_GWEI", "30"))
    GAS_PRICE_MULTIPLIER = float(os.getenv("POLYGON_GAS_PRICE_MULTIPLIER", "1.1"))
    
    # Trading Configuration
    MIN_PROFIT_THRESHOLD = float(os.getenv("POLYGON_MIN_PROFIT_THRESHOLD", "0.3"))  # %
    MAX_SLIPPAGE = float(os.getenv("POLYGON_MAX_SLIPPAGE", "0.5"))  # %
    MAX_TRADE_SIZE_MATIC = float(os.getenv("POLYGON_MAX_TRADE_SIZE", "1000.0"))
    
    # DEX Addresses (Polygon)
    UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
    UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    UNISWAP_V3_QUOTER_V2 = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
    
    QUICKSWAP_V2_ROUTER = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"
    QUICKSWAP_V2_FACTORY = "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32"
    
    SUSHISWAP_ROUTER = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
    SUSHISWAP_FACTORY = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"
    
    CURVE_REGISTRY = "0x094d12e5b541784701FD8d65F11fc0598FBC6332"
    
    # Flash Loan Providers (Polygon)
    AAVE_V3_LENDING_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
    AAVE_V3_PRICE_ORACLE = "0xb023e699F5a33916Ea823A16485e259257cA8Bd1"
    
    # Common Tokens (Polygon addresses)
    TOKENS = {
        "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "QUICK": "0x831753DD7087CaC61aB5644b308642cc1c33Dc13",
        "SUSHI": "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",
        "CRV": "0x172370d5Cd63279eFa6d502DAB29171933a610AF"
    }
    
    # Mempool Configuration
    MEMPOOL_MONITOR_ENABLED = os.getenv("POLYGON_MEMPOOL_MONITOR", "False") == "True"
    MIN_MEV_OPPORTUNITY_USD = float(os.getenv("POLYGON_MIN_MEV_OPPORTUNITY", "30.0"))
    
    @classmethod
    def validate(cls):
        errors = []
        if not cls.RPC_URL:
            errors.append("POLYGON_RPC_URL not properly configured")
        if not cls.PRIVATE_KEY:
            errors.append("POLYGON_PRIVATE_KEY not set")
        if errors:
            raise RuntimeError(f"Polygon config validation errors: {'; '.join(errors)}")