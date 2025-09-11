import os
from typing import List, Dict

class SolanaConfig:
    # Network Configuration
    NETWORK = os.getenv("SOLANA_NETWORK", "mainnet-beta")  # mainnet-beta, devnet, testnet
    RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    WSS_URL = os.getenv("SOLANA_WSS_URL", "wss://api.mainnet-beta.solana.com")
    
    # Wallet Configuration
    PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", "")  # Base58 encoded private key
    WALLET_ADDRESS = os.getenv("SOLANA_WALLET_ADDRESS", "")  # Public key
    
    # Transaction Configuration
    MAX_COMPUTE_UNITS = int(os.getenv("SOLANA_MAX_COMPUTE_UNITS", "400000"))
    COMPUTE_UNIT_PRICE = int(os.getenv("SOLANA_COMPUTE_UNIT_PRICE", "1000"))  # micro-lamports
    PRIORITY_FEE_LAMPORTS = int(os.getenv("SOLANA_PRIORITY_FEE", "5000"))
    
    # Trading Configuration
    MIN_PROFIT_THRESHOLD = float(os.getenv("SOLANA_MIN_PROFIT_THRESHOLD", "0.3"))  # %
    MAX_SLIPPAGE = float(os.getenv("SOLANA_MAX_SLIPPAGE", "0.5"))  # %
    MAX_TRADE_SIZE_SOL = float(os.getenv("SOLANA_MAX_TRADE_SIZE", "100.0"))
    
    # DEX Program IDs (Solana)
    JUPITER_AGGREGATOR = "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB"
    JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    
    RAYDIUM_AMM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    RAYDIUM_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUQzaMBFhfgv2B6VDw"
    
    ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    ORCA_LEGACY = "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP"
    
    SERUM_V3 = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
    
    # Flash Loan Program IDs
    MANGO_V4 = "4MangoMjqJ2firMokCjjGgoK8d4MXcrgL7XJaL3w6fVg"
    SOLEND = "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo"
    
    # Common SPL Tokens (Solana addresses)
    TOKENS = {
        "SOL": "So11111111111111111111111111111111111111112",  # Wrapped SOL
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "SRM": "SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKWRt",
        "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
        "MNGO": "MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac",
        "BTC": "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",  # Bitcoin (Sollet)
        "ETH": "2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk",  # Ethereum (Sollet)
        "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    }
    
    # Mempool Configuration
    MEMPOOL_MONITOR_ENABLED = os.getenv("SOLANA_MEMPOOL_MONITOR", "False") == "True"
    MIN_MEV_OPPORTUNITY_USD = float(os.getenv("SOLANA_MIN_MEV_OPPORTUNITY", "25.0"))
    
    # Solana-specific constants
    LAMPORTS_PER_SOL = 1_000_000_000
    WSOL_MINT = "So11111111111111111111111111111111111111112"
    
    @classmethod
    def validate(cls):
        errors = []
        if not cls.RPC_URL:
            errors.append("SOLANA_RPC_URL not properly configured")
        if not cls.PRIVATE_KEY:
            errors.append("SOLANA_PRIVATE_KEY not set")
        if errors:
            raise RuntimeError(f"Solana config validation errors: {'; '.join(errors)}")