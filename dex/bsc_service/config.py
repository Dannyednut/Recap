import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from network_config import NetworkConfig

class BSCConfig:
    # Get network configuration from centralized config
    _network_config = NetworkConfig.get_bsc_config()
    
    # Network Configuration
    CHAIN_ID = _network_config["chain_id"]
    RPC_URL = _network_config["rpc_url"]
    WSS_URL = _network_config["ws_url"]
    
    # Wallet Configuration
    PRIVATE_KEY = os.getenv("BSC_PRIVATE_KEY", "")
    WALLET_ADDRESS = os.getenv("BSC_WALLET_ADDRESS", "")
    
    # Gas Configuration
    MAX_GAS_PRICE_GWEI = int(os.getenv("BSC_MAX_GAS_PRICE_GWEI", "20"))
    GAS_PRICE_MULTIPLIER = float(os.getenv("BSC_GAS_PRICE_MULTIPLIER", "1.1"))
    
    # Trading Configuration
    MIN_PROFIT_THRESHOLD = float(os.getenv("BSC_MIN_PROFIT_THRESHOLD", "0.3"))  # %
    MAX_SLIPPAGE = float(os.getenv("BSC_MAX_SLIPPAGE", "0.5"))  # %
    MAX_TRADE_SIZE_BNB = float(os.getenv("BSC_MAX_TRADE_SIZE", "5.0"))
    
    # DEX Configuration (automatically switches based on MAINNET setting)
    PANCAKESWAP_V2_ROUTER = _network_config["dexes"]["pancakeswap_v2"]["router"]
    PANCAKESWAP_V2_FACTORY = _network_config["dexes"]["pancakeswap_v2"]["factory"]
    
    PANCAKESWAP_V3_ROUTER = _network_config["dexes"].get("pancakeswap_v3", {}).get("router", "")
    PANCAKESWAP_V3_FACTORY = _network_config["dexes"].get("pancakeswap_v3", {}).get("factory", "")
    
    BISWAP_ROUTER = _network_config["dexes"].get("biswap", {}).get("router", "")
    BISWAP_FACTORY = _network_config["dexes"].get("biswap", {}).get("factory", "")
    
    APESWAP_ROUTER = _network_config["dexes"].get("apeswap", {}).get("router", "")
    APESWAP_FACTORY = _network_config["dexes"].get("apeswap", {}).get("factory", "")
    
    # Token addresses (automatically switches based on MAINNET setting)
    TOKENS = _network_config["tokens"]
    
    # Flash Loan Providers (BSC)
    VENUS_COMPTROLLER = "0xfD36E2c2a6789Db23113685031d7F16329158384"
    ALPACA_LENDING_POOL = "0x0895196562C7868C5Be92459FaE7f877ED450452"
    
    # Mempool Configuration
    MEMPOOL_MONITOR_ENABLED = os.getenv("BSC_MEMPOOL_MONITOR", "False") == "True"
    MIN_MEV_OPPORTUNITY_USD = float(os.getenv("BSC_MIN_MEV_OPPORTUNITY", "50.0"))
    
    @classmethod
    def validate(cls):
        errors = []
        if not cls.RPC_URL:
            errors.append("BSC_RPC_URL not properly configured")
        if not cls.PRIVATE_KEY:
            errors.append("BSC_PRIVATE_KEY not set")
        if errors:
            raise RuntimeError(f"BSC config validation errors: {'; '.join(errors)}")