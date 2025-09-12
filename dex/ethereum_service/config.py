import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from network_config import NetworkConfig

class EthereumConfig:
    # Get network configuration from centralized config
    _network_config = NetworkConfig.get_ethereum_config()
    
    # Network Configuration
    CHAIN_ID = _network_config["chain_id"]
    RPC_URL = _network_config["rpc_url"]
    WSS_URL = _network_config["ws_url"]
    
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
    
    # DEX Configuration (automatically switches based on MAINNET setting)
    UNISWAP_V2_ROUTER = _network_config["dexes"]["uniswap_v2"]["router"]
    UNISWAP_V2_FACTORY = _network_config["dexes"]["uniswap_v2"]["factory"]
    
    UNISWAP_V3_ROUTER = _network_config["dexes"]["uniswap_v3"]["router"]
    UNISWAP_V3_FACTORY = _network_config["dexes"]["uniswap_v3"]["factory"]
    UNISWAP_V3_QUOTER_V2 = _network_config["dexes"]["uniswap_v3"]["quoter"]
    
    SUSHISWAP_ROUTER = _network_config["dexes"]["sushiswap"]["router"]
    SUSHISWAP_FACTORY = _network_config["dexes"]["sushiswap"]["factory"]
    
    # Flash Loan Providers
    AAVE_LENDING_POOL = "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9"
    DYDX_SOLO_MARGIN = "0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e"
    
    # Token addresses (automatically switches based on MAINNET setting)
    TOKENS = _network_config["tokens"]
    
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