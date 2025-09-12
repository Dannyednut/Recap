from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class ChainConfig:
    """Base configuration for blockchain connections"""
    chain_id: int
    network_name: str
    rpc_url: str
    ws_url: Optional[str] = None
    private_key: Optional[str] = None
    gas_limit: int = 3000000
    gas_price_multiplier: float = 1.1  # 10% buffer
    confirmation_blocks: int = 1
    max_fee_per_gas: Optional[int] = None
    max_priority_fee_per_gas: Optional[int] = None
    native_token_symbol: str = "ETH"
    wrapped_native_token: Optional[str] = None
    block_time: float = 15.0  # seconds
    explorer_url: Optional[str] = None
    mempool_enabled: bool = True
    flashloan_enabled: bool = True
    min_profit_threshold: float = 0.001  # 0.1%
    use_flashloan_by_default: bool = True
    max_slippage: float = 0.005  # 0.5%
    max_gas_price: Optional[int] = None
    retry_count: int = 3
    retry_delay: float = 1.0  # seconds
    timeout: float = 30.0  # seconds
    
    # DEX-specific configurations
    dex_configs: Dict[str, Any] = field(default_factory=dict)
    
    # Flashloan provider configurations
    flashloan_providers: Dict[str, Any] = field(default_factory=dict)
    
    # Token whitelist/blacklist
    token_whitelist: Optional[List[str]] = None
    token_blacklist: Optional[List[str]] = None
    
    # Contract addresses
    contract_addresses: Dict[str, str] = field(default_factory=dict)
    
    # Custom chain-specific settings
    custom_settings: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EthereumConfig(ChainConfig):
    """Ethereum-specific configuration"""
    chain_id: int = 1
    network_name: str = "ethereum"
    rpc_url: str = "https://mainnet.infura.io/v3/YOUR_INFURA_KEY"
    ws_url: Optional[str] = "wss://mainnet.infura.io/ws/v3/YOUR_INFURA_KEY"
    native_token_symbol: str = "ETH"
    wrapped_native_token: str = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH
    block_time: float = 12.0
    explorer_url: str = "https://etherscan.io"
    
    def __post_init__(self):
        # Initialize DEX configurations if not provided
        if not self.dex_configs:
            self.dex_configs = {
                "uniswap_v2": {
                    "router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                    "factory": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                },
                "uniswap_v3": {
                    "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                    "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                    "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
                },
                "sushiswap": {
                    "router": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
                    "factory": "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac",
                },
            }
        
        # Initialize flashloan provider configurations if not provided
        if not self.flashloan_providers:
            self.flashloan_providers = {
                "aave": {
                    "lending_pool": "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9",
                    "fee_percent": 0.0009,  # 0.09%
                },
                "dydx": {
                    "solo_margin": "0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e",
                    "fee_percent": 0.0,  # 0%
                },
                "balancer": {
                    "vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
                    "fee_percent": 0.0,  # 0%
                },
            }
        
        # Initialize contract addresses if not provided
        if not self.contract_addresses:
            self.contract_addresses = {
                "arbitrage_executor": "",  # To be deployed or loaded
                "weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                "usdc": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "usdt": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "dai": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            }

@dataclass
class BSCConfig(ChainConfig):
    """Binance Smart Chain-specific configuration"""
    chain_id: int = 56
    network_name: str = "bsc"
    rpc_url: str = "https://bsc-dataseed.binance.org/"
    ws_url: Optional[str] = "wss://bsc-ws-node.nariox.org:443"
    native_token_symbol: str = "BNB"
    wrapped_native_token: str = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"  # WBNB
    block_time: float = 3.0
    explorer_url: str = "https://bscscan.com"
    
    def __post_init__(self):
        # Initialize DEX configurations if not provided
        if not self.dex_configs:
            self.dex_configs = {
                "pancakeswap_v2": {
                    "router": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
                    "factory": "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73",
                },
                "biswap": {
                    "router": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",
                    "factory": "0x858E3312ed3A876947EA49d572A7C42DE08af7EE",
                },
                "mdex": {
                    "router": "0x7DAe51BD3E3376B8c7c4900E9107f12Be3AF1bA8",
                    "factory": "0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8",
                },
            }
        
        # Initialize flashloan provider configurations if not provided
        if not self.flashloan_providers:
            self.flashloan_providers = {
                "venus": {
                    "controller": "0xfD36E2c2a6789Db23113685031d7F16329158384",
                    "fee_percent": 0.0009,  # 0.09%
                },
                "pancakeswap": {
                    "router": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
                    "fee_percent": 0.0025,  # 0.25%
                },
            }
        
        # Initialize contract addresses if not provided
        if not self.contract_addresses:
            self.contract_addresses = {
                "arbitrage_executor": "",  # To be deployed or loaded
                "wbnb": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
                "busd": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
                "usdt": "0x55d398326f99059fF775485246999027B3197955",
                "usdc": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
            }

@dataclass
class PolygonConfig(ChainConfig):
    """Polygon-specific configuration"""
    chain_id: int = 137
    network_name: str = "polygon"
    rpc_url: str = "https://polygon-rpc.com"
    ws_url: Optional[str] = "wss://polygon-ws.nariox.org:443"
    native_token_symbol: str = "MATIC"
    wrapped_native_token: str = "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"  # WMATIC
    block_time: float = 2.0
    explorer_url: str = "https://polygonscan.com"
    
    def __post_init__(self):
        # Initialize DEX configurations if not provided
        if not self.dex_configs:
            self.dex_configs = {
                "quickswap": {
                    "router": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
                    "factory": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
                },
                "sushiswap": {
                    "router": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
                    "factory": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
                },
                "uniswap_v3": {
                    "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                    "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                    "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
                },
            }
        
        # Initialize flashloan provider configurations if not provided
        if not self.flashloan_providers:
            self.flashloan_providers = {
                "aave": {
                    "lending_pool": "0x8dFf5E27EA6b7AC08EbFdf9eB090F32ee9a30fcf",
                    "fee_percent": 0.0009,  # 0.09%
                },
                "balancer": {
                    "vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
                    "fee_percent": 0.0,  # 0%
                },
            }
        
        # Initialize contract addresses if not provided
        if not self.contract_addresses:
            self.contract_addresses = {
                "arbitrage_executor": "",  # To be deployed or loaded
                "wmatic": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
                "usdc": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                "usdt": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
                "dai": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
            }

@dataclass
class SolanaConfig(ChainConfig):
    """Solana-specific configuration"""
    chain_id: int = 0  # Not applicable for Solana
    network_name: str = "solana"
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    ws_url: Optional[str] = "wss://api.mainnet-beta.solana.com"
    native_token_symbol: str = "SOL"
    wrapped_native_token: str = "So11111111111111111111111111111111111111112"  # Wrapped SOL
    block_time: float = 0.4
    explorer_url: str = "https://explorer.solana.com"
    
    # Solana-specific fields
    commitment: str = "confirmed"
    keypair_path: Optional[str] = None
    
    def __post_init__(self):
        # Initialize DEX configurations if not provided
        if not self.dex_configs:
            self.dex_configs = {
                "raydium": {
                    "amm_program": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
                    "swap_program": "9qvG1zUp8xF1Bi4m6UdRNby1BAAuaDrUxSpv4CmRRMjL",
                },
                "orca": {
                    "swap_program": "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP",
                },
                "jupiter": {
                    "aggregator": "JUP2jxvXaqu7NQY1GmNF4m1vodw12LVXYxbFL2uJvfo",
                },
            }
        
        # Initialize flashloan provider configurations if not provided
        if not self.flashloan_providers:
            self.flashloan_providers = {
                "solend": {
                    "program": "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo",
                    "fee_percent": 0.0,  # 0%
                },
                "port": {
                    "program": "Port7uDYB3wk6GJAw4KT1WpTeMtSu9bTcChBHkX2LfR",
                    "fee_percent": 0.0,  # 0%
                },
            }
        
        # Initialize contract addresses (program IDs) if not provided
        if not self.contract_addresses:
            self.contract_addresses = {
                "arbitrage_executor": "",  # To be deployed or loaded
                "wsol": "So11111111111111111111111111111111111111112",
                "usdc": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "usdt": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            }