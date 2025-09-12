import asyncio
import logging
from typing import Dict, List, Set, Any, Optional
from web3 import AsyncWeb3
import json
import os
import aiohttp
from decimal import Decimal

from .config import EthereumConfig
from .protocols.uniswap_v2_adapter import UniswapV2Adapter
from .protocols.uniswap_v3_adapter import UniswapV3Adapter

logger = logging.getLogger(__name__)

class EthereumTokenDiscoveryService:
    """Dynamic token and pair discovery service for DEX arbitrage"""
    
    def __init__(self, engine, config: EthereumConfig):
        self.engine = engine
        self.w3 = engine.w3
        self.config = config
        
        # Protocol adapters
        self.uniswap_v2 = None
        self.uniswap_v3 = None
        self.sushiswap = None
        
        # Token and pair storage
        self.discovered_tokens = set()
        self.token_metadata = {}  # address -> {name, symbol, decimals}
        self.active_pairs = {}  # dex -> {pair_address -> {token0, token1, reserves, fee}}
        
        # Liquidity thresholds
        self.min_liquidity_usd = Decimal("10000")  # $10k minimum liquidity
        
        # Cache directory
        self.cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        
    async def initialize(self):
        """Initialize token discovery service"""
        logger.info("Initializing token discovery service...")
        
        # Initialize protocol adapters
        self.uniswap_v2 = UniswapV2Adapter(self.w3, self.config.UNISWAP_V2_FACTORY, self.config.UNISWAP_V2_ROUTER)
        self.uniswap_v3 = UniswapV3Adapter(self.w3, self.config.UNISWAP_V3_FACTORY, self.config.UNISWAP_V3_ROUTER)
        self.sushiswap = UniswapV2Adapter(self.w3, self.config.SUSHISWAP_FACTORY, self.config.SUSHISWAP_ROUTER)
        
        # Load cached tokens and pairs if available
        await self._load_cached_data()
        
    async def start_discovery(self):
        """Start continuous token and pair discovery"""
        logger.info("Starting token and pair discovery...")
        
        try:
            # Initial discovery of major tokens and pairs
            await self._discover_initial_tokens()
            
            # Start continuous discovery tasks
            discovery_task = asyncio.create_task(self._continuous_discovery())
            
            return discovery_task
            
        except Exception as e:
            logger.error(f"Error in token discovery: {e}")
    
    async def get_active_pairs(self, dex: str = None) -> Dict:
        """Get active pairs, optionally filtered by DEX"""
        if dex:
            return self.active_pairs.get(dex, {})
        return self.active_pairs
    
    async def get_token_metadata(self, token_address: str) -> Dict:
        """Get token metadata"""
        if token_address in self.token_metadata:
            return self.token_metadata[token_address]
            
        # Fetch metadata if not in cache
        try:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.loads(open(os.path.join(os.path.dirname(__file__), 'abis', 'erc20.json')).read())
            )
            
            name = await token_contract.functions.name().call()
            symbol = await token_contract.functions.symbol().call()
            decimals = await token_contract.functions.decimals().call()
            
            metadata = {
                "name": name,
                "symbol": symbol,
                "decimals": decimals
            }
            
            self.token_metadata[token_address] = metadata
            return metadata
            
        except Exception as e:
            logger.error(f"Error fetching token metadata for {token_address}: {e}")
            return {"name": "Unknown", "symbol": "???", "decimals": 18}
    
    async def _discover_initial_tokens(self):
        """Discover initial set of tokens and pairs"""
        # Start with well-known tokens
        initial_tokens = [
            self.config.TOKENS["WETH"],
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"],
            self.config.TOKENS["DAI"],
            self.config.TOKENS["WBTC"]
        ]
        
        for token in initial_tokens:
            self.discovered_tokens.add(token)
            await self.get_token_metadata(token)
        
        # Discover pairs for these tokens
        await self._discover_pairs_for_tokens(initial_tokens)
    
    async def _discover_pairs_for_tokens(self, tokens: List[str]):
        """Discover pairs for a list of tokens across all DEXes"""
        # Discover Uniswap V2 pairs
        v2_pairs = await self.uniswap_v2.get_pairs_for_tokens(tokens)
        await self._process_discovered_pairs("uniswap_v2", v2_pairs)
        
        # Discover Uniswap V3 pools
        v3_pairs = await self.uniswap_v3.get_pairs_for_tokens(tokens)
        await self._process_discovered_pairs("uniswap_v3", v3_pairs)
        
        # Discover SushiSwap pairs
        sushi_pairs = await self.sushiswap.get_pairs_for_tokens(tokens)
        await self._process_discovered_pairs("sushiswap", sushi_pairs)
    
    async def _process_discovered_pairs(self, dex: str, pairs: Dict):
        """Process discovered pairs and extract new tokens"""
        if dex not in self.active_pairs:
            self.active_pairs[dex] = {}
            
        new_tokens = set()
        
        for pair_address, pair_data in pairs.items():
            # Add pair to active pairs
            self.active_pairs[dex][pair_address] = pair_data
            
            # Extract tokens
            token0 = pair_data["token0"]
            token1 = pair_data["token1"]
            
            # Add to discovered tokens
            if token0 not in self.discovered_tokens:
                self.discovered_tokens.add(token0)
                new_tokens.add(token0)
                
            if token1 not in self.discovered_tokens:
                self.discovered_tokens.add(token1)
                new_tokens.add(token1)
        
        # Get metadata for new tokens
        for token in new_tokens:
            await self.get_token_metadata(token)
            
        # Save to cache
        await self._save_cached_data()
        
        logger.info(f"Discovered {len(pairs)} pairs on {dex}, {len(new_tokens)} new tokens")
    
    async def _continuous_discovery(self):
        """Continuously discover new tokens and pairs"""
        while True:
            try:
                # Get current token list
                tokens_to_check = list(self.discovered_tokens)
                
                # Discover new pairs in batches
                batch_size = 10
                for i in range(0, len(tokens_to_check), batch_size):
                    batch = tokens_to_check[i:i+batch_size]
                    await self._discover_pairs_for_tokens(batch)
                
                # Sleep before next discovery round
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                logger.error(f"Error in continuous discovery: {e}")
                await asyncio.sleep(60)  # Retry after a minute
    
    async def _load_cached_data(self):
        """Load cached token and pair data"""
        try:
            # Load token metadata
            token_cache_path = os.path.join(self.cache_dir, 'token_metadata.json')
            if os.path.exists(token_cache_path):
                with open(token_cache_path, 'r') as f:
                    self.token_metadata = json.load(f)
                    self.discovered_tokens = set(self.token_metadata.keys())
                    
            # Load pair data
            pairs_cache_path = os.path.join(self.cache_dir, 'active_pairs.json')
            if os.path.exists(pairs_cache_path):
                with open(pairs_cache_path, 'r') as f:
                    self.active_pairs = json.load(f)
                    
            logger.info(f"Loaded {len(self.discovered_tokens)} tokens and {sum(len(pairs) for pairs in self.active_pairs.values())} pairs from cache")
            
        except Exception as e:
            logger.error(f"Error loading cached data: {e}")
    
    async def _save_cached_data(self):
        """Save token and pair data to cache"""
        try:
            # Save token metadata
            token_cache_path = os.path.join(self.cache_dir, 'token_metadata.json')
            with open(token_cache_path, 'w') as f:
                json.dump(self.token_metadata, f)
                
            # Save pair data
            pairs_cache_path = os.path.join(self.cache_dir, 'active_pairs.json')
            with open(pairs_cache_path, 'w') as f:
                json.dump(self.active_pairs, f)
                
        except Exception as e:
            logger.error(f"Error saving cached data: {e}")