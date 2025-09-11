import os
from typing import List, Dict

class BSCConfig:
    # Network Configuration
    CHAIN_ID = int(os.getenv("BSC_CHAIN_ID", "56"))  # 56=mainnet, 97=testnet
    RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed1.binance.org/")
    WSS_URL = os.getenv("BSC_WSS_URL", "wss://bsc-ws-node.nariox.org:443")
    
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
    
    # DEX Addresses (BSC)
    PANCAKESWAP_V2_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
    PANCAKESWAP_V2_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    PANCAKESWAP_V3_ROUTER = "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"
    PANCAKESWAP_V3_FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
    PANCAKESWAP_V3_QUOTER_V2 = "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997"
    
    BISWAP_ROUTER = "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8"
    BISWAP_FACTORY = "0x858E3312ed3A876947EA49d572A7C42DE08af7EE"
    
    APESWAP_ROUTER = "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7"
    APESWAP_FACTORY = "0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6"
    
    # Flash Loan Providers (BSC)
    VENUS_COMPTROLLER = "0xfD36E2c2a6789Db23113685031d7F16329158384"
    ALPACA_LENDING_POOL = "0x0895196562C7868C5Be92459FaE7f877ED450452"
    
    # Common Tokens (BSC addresses)
    TOKENS = {
        "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
        "USDT": "0x55d398326f99059fF775485246999027B3197955",
        "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "ETH": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
        "BTCB": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
        "CAKE": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
    }
    
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