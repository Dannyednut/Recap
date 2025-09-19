import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List, Set
from web3 import AsyncWeb3
from web3.contract import AsyncContract
from datetime import datetime
import os

# Import shared models and utilities
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dex.shared.models.arbitrage_models import Token, DexPair
from dex.shared.contract_addresses import get_chain_addresses, get_base_tokens, get_router_address, get_factory_address, get_network_name
from dex.shared.abi_fetcher import ABIFetcher, FALLBACK_ABIS

from .config import BSCConfig
from .engine import BSCEngine

logger = logging.getLogger(__name__)

class BSCTokenDiscoveryService:
    """Token discovery service for BSC - finds profitable trading pairs"""
    
    def __init__(self, engine: BSCEngine, config: BSCConfig):
        self.engine = engine
        self.config = config
        
        # Token tracking
        self.discovered_tokens: Dict[str, Token] = {}
        self.active_pairs: List[DexPair] = []
        self.pair_volumes: Dict[str, Decimal] = {}
        self.pair_last_updated: Dict[str, datetime] = {}
        
        # Discovery settings
        self.min_liquidity_usd = Decimal("10000")  # $10k minimum liquidity
        self.min_volume_24h_usd = Decimal("50000")  # $50k minimum 24h volume
        self.max_tokens_to_track = 500
        
        # Get network-aware addresses
        self.chain_addresses = get_chain_addresses('bsc')
        self.network_name = get_network_name('bsc')
        
        # BSC DEX routers (network-aware)
        self.dex_routers = self.chain_addresses.get('routers', {})
        
        # BSC DEX factories (network-aware)
        self.dex_factories = self.chain_addresses.get('factories', {})
        
        # Popular BSC tokens to monitor (network-aware)
        self.base_tokens = get_base_tokens('bsc')
        
        # ABI fetcher for dynamic contract interaction
        self.abi_fetcher = ABIFetcher()
        
        self.is_running = False
        self.discovery_task = None
        
    async def initialize(self) -> bool:
        """Initialize the token discovery service"""
        try:
            logger.info("Initializing BSC Token Discovery Service...")
            
            # Initialize ABI fetcher
            await self.abi_fetcher.__aenter__()
            
            # Initialize base tokens with dynamic ABI fetching
            for symbol, address in self.base_tokens.items():
                # Get token info using dynamic ABI
                token_info = await self._get_token_info(address)
                if token_info:
                    token = Token(
                        address=address,
                        symbol=token_info.get('symbol', symbol),
                        decimals=token_info.get('decimals', 18),
                        name=token_info.get('name', symbol)
                    )
                    self.discovered_tokens[address] = token
                else:
                    # Fallback to basic token info
                    token = Token(
                        address=address,
                        symbol=symbol,
                        decimals=18,
                        name=symbol
                    )
                    self.discovered_tokens[address] = token
            
            # Get actual token details
            await self._update_token_details()
            
            logger.info(f"BSC Token Discovery Service initialized with {len(self.discovered_tokens)} base tokens")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize BSC Token Discovery Service: {e}")
            return False
    
    async def _get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get token information using dynamic ABI fetching"""
        try:
            # Try to fetch ABI from BSCScan
            abi = await self.abi_fetcher.fetch_abi('bsc', self.network_name, token_address)
            
            if not abi:
                # Use fallback ERC20 ABI
                abi = FALLBACK_ABIS['erc20']
            
            # Create contract instance
            contract = self.engine.w3.eth.contract(
                address=self.engine.w3.to_checksum_address(token_address),
                abi=abi
            )
            
            # Get token details
            try:
                name = await contract.functions.name().call()
                symbol = await contract.functions.symbol().call()
                decimals = await contract.functions.decimals().call()
                
                return {
                    'name': name,
                    'symbol': symbol,
                    'decimals': decimals,
                    'abi': abi
                }
            except Exception as e:
                logger.warning(f"Failed to get token details for {token_address}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting token info for {token_address}: {e}")
            return None
    
    async def start(self):
        """Start the token discovery service"""
        if self.is_running:
            logger.warning("BSC Token Discovery Service is already running")
            return
        
        self.is_running = True
        self.discovery_task = asyncio.create_task(self._discovery_loop())
        logger.info("BSC Token Discovery Service started")
    
    async def stop(self):
        """Stop the token discovery service"""
        self.is_running = False
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
        logger.info("BSC Token Discovery Service stopped")
    
    async def _discovery_loop(self):
        """Main discovery loop"""
        while self.is_running:
            try:
                # Discover new tokens from DEX events
                await self._discover_from_dex_events()
                
                # Update pair information
                await self._update_pair_info()
                
                # Clean up inactive pairs
                await self._cleanup_inactive_pairs()
                
                # Sleep before next discovery cycle
                await asyncio.sleep(300)  # 5 minutes between discovery cycles
                
            except Exception as e:
                logger.error(f"Error in BSC token discovery loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def _discover_from_dex_events(self):
        """Discover new tokens from DEX swap events"""
        try:
            # Get recent blocks to scan for new pairs
            latest_block = await self.engine.w3.eth.get_block_number()
            from_block = latest_block - 1000  # Scan last 1000 blocks (~50 minutes on BSC)
            
            # Scan PancakeSwap V2 for new pairs
            await self._scan_pancakeswap_pairs(from_block, latest_block)
            
        except Exception as e:
            logger.error(f"Error discovering tokens from DEX events: {e}")
    
    async def _scan_pancakeswap_pairs(self, from_block: int, to_block: int):
        """Scan PancakeSwap for new trading pairs"""
        try:
            # PancakeSwap V2 Factory contract
            factory_address = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
            
            # PairCreated event signature
            pair_created_topic = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
            
            # Get PairCreated events
            filter_params = {
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": factory_address,
                "topics": [pair_created_topic]
            }
            
            events = await self.engine.w3.eth.get_logs(filter_params)
            
            for event in events:
                try:
                    # Decode pair creation event
                    token0 = "0x" + event.data[26:66]
                    token1 = "0x" + event.data[90:130]
                    pair_address = "0x" + event.data[154:194]
                    
                    # Add tokens to discovery if not already tracked
                    await self._add_token_if_viable(token0)
                    await self._add_token_if_viable(token1)
                    
                    # Create pair if both tokens are viable
                    if token0 in self.discovered_tokens and token1 in self.discovered_tokens:
                        await self._add_trading_pair(token0, token1, pair_address)
                        
                except Exception as e:
                    logger.error(f"Error processing pair creation event: {e}")
                    
        except Exception as e:
            logger.error(f"Error scanning PancakeSwap pairs: {e}")
    
    async def _add_token_if_viable(self, token_address: str):
        """Add token to tracking if it meets viability criteria"""
        try:
            if token_address in self.discovered_tokens:
                return
            
            if len(self.discovered_tokens) >= self.max_tokens_to_track:
                return
            
            # Get token details
            token_details = await self._get_token_details(token_address)
            if not token_details:
                return
            
            # Check if token has sufficient liquidity
            liquidity_usd = await self._get_token_liquidity_usd(token_address)
            if liquidity_usd < self.min_liquidity_usd:
                return
            
            # Add token to tracking
            token = Token(
                address=token_address,
                symbol=token_details["symbol"],
                decimals=token_details["decimals"],
                name=token_details["name"]
            )
            
            self.discovered_tokens[token_address] = token
            logger.info(f"Added new BSC token: {token.symbol} ({token_address})")
            
        except Exception as e:
            logger.error(f"Error adding token {token_address}: {e}")
    
    async def _get_token_details(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get token details from contract"""
        try:
            # Standard ERC20 ABI for basic info
            erc20_abi = [
                {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
            ]
            
            contract = self.engine.w3.eth.contract(address=token_address, abi=erc20_abi)
            
            name = await contract.functions.name().call()
            symbol = await contract.functions.symbol().call()
            decimals = await contract.functions.decimals().call()
            
            return {
                "name": name,
                "symbol": symbol,
                "decimals": decimals
            }
            
        except Exception as e:
            logger.error(f"Error getting token details for {token_address}: {e}")
            return None
    
    async def _get_token_liquidity_usd(self, token_address: str) -> Decimal:
        """Get token's total liquidity in USD"""
        try:
            # This is a simplified implementation
            # In production, you'd query multiple DEXs and aggregate liquidity
            
            # For now, return a placeholder value
            # You would implement actual liquidity checking here
            return Decimal("50000")  # Placeholder
            
        except Exception as e:
            logger.error(f"Error getting liquidity for {token_address}: {e}")
            return Decimal("0")
    
    async def _add_trading_pair(self, token0: str, token1: str, pair_address: str):
        """Add a trading pair to active pairs"""
        try:
            # Create pair object
            pair = DexPair(
                address=pair_address,
                token0=self.discovered_tokens[token0],
                token1=self.discovered_tokens[token1],
                dex="pancakeswap_v2",
                router_address=self.dex_routers["pancakeswap_v2"],
                fee=0.0025  # 0.25% fee for PancakeSwap V2
            )
            
            # Check if pair already exists
            pair_key = f"{token0}-{token1}-{pair_address}"
            if not any(p.address == pair_address for p in self.active_pairs):
                self.active_pairs.append(pair)
                self.pair_last_updated[pair_key] = datetime.now()
                logger.info(f"Added new BSC trading pair: {pair.token0.symbol}/{pair.token1.symbol}")
            
        except Exception as e:
            logger.error(f"Error adding trading pair: {e}")
    
    async def _update_pair_info(self):
        """Update information for active pairs"""
        try:
            for pair in self.active_pairs:
                pair_key = f"{pair.token0.address}-{pair.token1.address}-{pair.address}"
                
                # Update volume information
                volume_24h = await self._get_pair_volume_24h(pair)
                self.pair_volumes[pair_key] = volume_24h
                self.pair_last_updated[pair_key] = datetime.now()
                
        except Exception as e:
            logger.error(f"Error updating pair info: {e}")
    
    async def _get_pair_volume_24h(self, pair: DexPair) -> Decimal:
        """Get 24h volume for a trading pair"""
        try:
            # This is a placeholder implementation
            # In production, you'd query DEX APIs or analyze on-chain events
            return Decimal("100000")  # Placeholder volume
            
        except Exception as e:
            logger.error(f"Error getting pair volume: {e}")
            return Decimal("0")
    
    async def _cleanup_inactive_pairs(self):
        """Remove pairs that haven't been active recently"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            # Remove pairs with low volume or old data
            active_pairs = []
            for pair in self.active_pairs:
                pair_key = f"{pair.token0.address}-{pair.token1.address}-{pair.address}"
                
                last_updated = self.pair_last_updated.get(pair_key, datetime.min)
                volume = self.pair_volumes.get(pair_key, Decimal("0"))
                
                if last_updated > cutoff_time and volume > self.min_volume_24h_usd:
                    active_pairs.append(pair)
                else:
                    logger.info(f"Removing inactive BSC pair: {pair.token0.symbol}/{pair.token1.symbol}")
            
            self.active_pairs = active_pairs
            
        except Exception as e:
            logger.error(f"Error cleaning up inactive pairs: {e}")
    
    async def _update_token_details(self):
        """Update details for tracked tokens"""
        try:
            for address, token in self.discovered_tokens.items():
                if token.decimals == 18:  # Default value, needs updating
                    details = await self._get_token_details(address)
                    if details:
                        token.decimals = details["decimals"]
                        token.name = details["name"]
                        
        except Exception as e:
            logger.error(f"Error updating token details: {e}")
    
    # Public interface methods
    async def get_active_pairs(self) -> List[DexPair]:
        """Get list of active trading pairs"""
        return self.active_pairs.copy()
    
    async def get_discovered_tokens(self) -> Dict[str, Token]:
        """Get all discovered tokens"""
        return self.discovered_tokens.copy()
    
    async def get_pair_volume(self, pair_address: str) -> Decimal:
        """Get volume for a specific pair"""
        for pair in self.active_pairs:
            if pair.address == pair_address:
                pair_key = f"{pair.token0.address}-{pair.token1.address}-{pair.address}"
                return self.pair_volumes.get(pair_key, Decimal("0"))
        return Decimal("0")
    
    async def is_token_viable(self, token_address: str) -> bool:
        """Check if a token is viable for arbitrage"""
        return token_address in self.discovered_tokens
    
    def get_stats(self) -> Dict[str, Any]:
        """Get discovery service statistics"""
        return {
            "discovered_tokens": len(self.discovered_tokens),
            "active_pairs": len(self.active_pairs),
            "total_volume_24h": float(sum(self.pair_volumes.values())),
            "last_discovery_run": max(self.pair_last_updated.values()).isoformat() if self.pair_last_updated else None
        }
