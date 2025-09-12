import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from network_config import NetworkConfig

class PolygonConfig:
    # Get network configuration from centralized config
    _network_config = NetworkConfig.get_polygon_config()
    
    # Network Configuration
    CHAIN_ID = _network_config["chain_id"]
    RPC_URL = _network_config["rpc_url"]
    WSS_URL = _network_config["ws_url"]
    
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
    
    # DEX Configuration (automatically switches based on MAINNET setting)
    UNISWAP_V3_ROUTER = _network_config["dexes"]["uniswap_v3"]["router"]
    UNISWAP_V3_FACTORY = _network_config["dexes"]["uniswap_v3"]["factory"]
    UNISWAP_V3_QUOTER_V2 = _network_config["dexes"]["uniswap_v3"]["quoter"]
    
    QUICKSWAP_ROUTER = _network_config["dexes"]["quickswap"]["router"]
    QUICKSWAP_FACTORY = _network_config["dexes"]["quickswap"]["factory"]
    
    SUSHISWAP_ROUTER = _network_config["dexes"]["sushiswap"]["router"]
    SUSHISWAP_FACTORY = _network_config["dexes"]["sushiswap"]["factory"]
    
    CURVE_REGISTRY = "0x094d12e5b541784701FD8d65F11fc0598FBC6332"
    
    # Flash Loan Providers (Polygon)
    AAVE_V3_LENDING_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
    AAVE_V3_PRICE_ORACLE = "0xb023e699F5a33916Ea823A16485e259257cA8Bd1"
    
    # Token addresses (automatically switches based on MAINNET setting)
    TOKENS = _network_config["tokens"]
    
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