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

from .config import PolygonConfig
from .engine import PolygonEngine

logger = logging.getLogger(__name__)

class PolygonTokenDiscoveryService:
    """Token discovery service for Polygon - finds profitable trading pairs"""
    
    def __init__(self, engine: PolygonEngine, config: PolygonConfig):
        self.engine = engine
        self.config = config
        
        # Token tracking
        self.discovered_tokens: Dict[str, Token] = {}
        self.active_pairs: List[DexPair] = []
        self.pair_volumes: Dict[str, Decimal] = {}
        self.pair_last_updated: Dict[str, datetime] = {}
        
        # Discovery settings
        self.min_liquidity_usd = Decimal("5000")   # $5k minimum liquidity
        self.min_volume_24h_usd = Decimal("25000") # $25k minimum 24h volume
        self.max_tokens_to_track = 750
        
        # Get network-aware addresses
        self.chain_addresses = get_chain_addresses('polygon')
        self.network_name = get_network_name('polygon')
        
        # Polygon DEX routers (network-aware)
        self.dex_routers = self.chain_addresses.get('routers', {})
        
        # Polygon DEX factories (network-aware)
        self.dex_factories = self.chain_addresses.get('factories', {})
        
        # Popular Polygon tokens to monitor (network-aware)
        self.base_tokens = get_base_tokens('polygon')
        
        # ABI fetcher for dynamic contract interaction
        self.abi_fetcher = ABIFetcher()
        
        self.is_running = False
        self.discovery_task = None
        
    async def initialize(self) -> bool:
        """Initialize the token discovery service"""
        try:
            logger.info("Initializing Polygon Token Discovery Service...")
            
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
            
            logger.info(f"Polygon Token Discovery Service initialized with {len(self.discovered_tokens)} base tokens")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Polygon Token Discovery Service: {e}")
            return False
    
    async def _get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get token information using dynamic ABI fetching"""
        try:
            # Try to fetch ABI from PolygonScan
            abi = await self.abi_fetcher.fetch_abi('polygon', self.network_name, token_address)
            
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
            logger.warning("Polygon Token Discovery Service is already running")
            return
        
        self.is_running = True
        self.discovery_task = asyncio.create_task(self._discovery_loop())
        logger.info("Polygon Token Discovery Service started")
    
    async def stop(self):
        """Stop the token discovery service"""
        self.is_running = False
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
        logger.info("Polygon Token Discovery Service stopped")
    
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
                await asyncio.sleep(240)  # 4 minutes between discovery cycles
                
            except Exception as e:
                logger.error(f"Error in Polygon token discovery loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def _discover_from_dex_events(self):
        """Discover new tokens from DEX swap events"""
        try:
            # Get recent blocks to scan for new pairs
            latest_block = await self.engine.w3.eth.get_block_number()
            from_block = latest_block - 800  # Scan last 800 blocks (~30 minutes on Polygon)
            
            # Scan QuickSwap for new pairs
            await self._scan_quickswap_pairs(from_block, latest_block)
            
            # Scan SushiSwap for new pairs
            await self._scan_sushiswap_pairs(from_block, latest_block)
            
        except Exception as e:
            logger.error(f"Error discovering tokens from DEX events: {e}")
    
    async def _scan_quickswap_pairs(self, from_block: int, to_block: int):
        """Scan QuickSwap for new trading pairs"""
        try:
            factory_address = self.dex_factories["quickswap"]
            
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
                        await self._add_trading_pair(token0, token1, pair_address, "quickswap")
                        
                except Exception as e:
                    logger.error(f"Error processing QuickSwap pair creation event: {e}")
                    
        except Exception as e:
            logger.error(f"Error scanning QuickSwap pairs: {e}")
    
    async def _scan_sushiswap_pairs(self, from_block: int, to_block: int):
        """Scan SushiSwap for new trading pairs"""
        try:
            factory_address = self.dex_factories["sushiswap"]
            
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
                        await self._add_trading_pair(token0, token1, pair_address, "sushiswap")
                        
                except Exception as e:
                    logger.error(f"Error processing SushiSwap pair creation event: {e}")
                    
        except Exception as e:
            logger.error(f"Error scanning SushiSwap pairs: {e}")
    
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
            logger.info(f"Added new Polygon token: {token.symbol} ({token_address})")
            
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
        """Get token's total liquidity in USD across all DEXs"""
        try:
            total_liquidity = Decimal("0")
            
            # Check liquidity on major DEXs
            for base_token_address in ["0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
                                      "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
                                      "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"]: # USDT
                
                # QuickSwap liquidity
                quickswap_liquidity = await self._get_pair_liquidity_usd(
                    token_address, base_token_address, "quickswap"
                )
                total_liquidity += quickswap_liquidity
                
                # SushiSwap liquidity
                sushiswap_liquidity = await self._get_pair_liquidity_usd(
                    token_address, base_token_address, "sushiswap"
                )
                total_liquidity += sushiswap_liquidity
            
            return total_liquidity
            
        except Exception as e:
            logger.error(f"Error getting liquidity for {token_address}: {e}")
            return Decimal("0")
    
    async def _get_pair_liquidity_usd(self, token0: str, token1: str, dex: str) -> Decimal:
        """Get liquidity for a specific pair on a DEX"""
        try:
            # Get pair address
            pair_address = await self._get_pair_address(token0, token1, dex)
            if not pair_address:
                return Decimal("0")
            
            # Get reserves
            reserves = await self._get_pair_reserves(pair_address)
            if not reserves:
                return Decimal("0")
            
            reserve0, reserve1 = reserves
            
            # Get token prices (simplified - would use price oracle in production)
            token0_price = await self._get_token_price_usd(token0)
            token1_price = await self._get_token_price_usd(token1)
            
            # Calculate total liquidity
            liquidity_usd = (reserve0 * token0_price) + (reserve1 * token1_price)
            
            return liquidity_usd
            
        except Exception as e:
            logger.error(f"Error getting pair liquidity: {e}")
            return Decimal("0")
    
    async def _get_pair_address(self, token0: str, token1: str, dex: str) -> Optional[str]:
        """Get pair address for tokens on a specific DEX"""
        try:
            factory_address = self.dex_factories.get(dex)
            if not factory_address:
                return None
            
            factory_abi = [
                {"constant": True, "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}], 
                 "name": "getPair", "outputs": [{"name": "pair", "type": "address"}], "type": "function"}
            ]
            
            factory_contract = self.engine.w3.eth.contract(address=factory_address, abi=factory_abi)
            pair_address = await factory_contract.functions.getPair(token0, token1).call()
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None
            
            return pair_address
            
        except Exception as e:
            logger.error(f"Error getting pair address: {e}")
            return None
    
    async def _get_pair_reserves(self, pair_address: str) -> Optional[tuple]:
        """Get reserves for a trading pair"""
        try:
            pair_abi = [
                {"constant": True, "inputs": [], "name": "getReserves", 
                 "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, 
                            {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"}
            ]
            
            pair_contract = self.engine.w3.eth.contract(address=pair_address, abi=pair_abi)
            reserves = await pair_contract.functions.getReserves().call()
            
            return Decimal(reserves[0]), Decimal(reserves[1])
            
        except Exception as e:
            logger.error(f"Error getting pair reserves: {e}")
            return None
    
    async def _get_token_price_usd(self, token_address: str) -> Decimal:
        """Get token price in USD"""
        try:
            # Common Polygon token prices (simplified implementation)
            token_prices = {
                "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270": Decimal("0.8"),   # WMATIC
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": Decimal("1.0"),   # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": Decimal("1.0"),   # USDT
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063": Decimal("1.0"),   # DAI
                "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619": Decimal("2500"), # WETH
                "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6": Decimal("45000"), # WBTC
                "0xD6DF932A45C0f255f85145f286eA0b292B21C90B": Decimal("80"),    # AAVE
                "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39": Decimal("15"),    # LINK
                "0xb33EaAd8d922B1083446DC23f610c2567fB5180f": Decimal("8"),     # UNI
                "0x172370d5Cd63279eFa6d502DAB29171933a610AF": Decimal("0.5")   # CRV
            }
            
            return token_prices.get(token_address, Decimal("1"))
            
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return Decimal("1")
    
    async def _add_trading_pair(self, token0: str, token1: str, pair_address: str, dex: str):
        """Add a trading pair to active pairs"""
        try:
            # Create pair object
            pair = DexPair(
                address=pair_address,
                token0=self.discovered_tokens[token0],
                token1=self.discovered_tokens[token1],
                dex=dex,
                router_address=self.dex_routers[dex],
                fee=0.003 if dex in ["quickswap", "sushiswap"] else 0.0005  # Default fees
            )
            
            # Check if pair already exists
            pair_key = f"{token0}-{token1}-{pair_address}"
            if not any(p.address == pair_address for p in self.active_pairs):
                self.active_pairs.append(pair)
                self.pair_last_updated[pair_key] = datetime.now()
                logger.info(f"Added new Polygon trading pair: {pair.token0.symbol}/{pair.token1.symbol} on {dex}")
            
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
            # This would typically query DEX APIs or analyze swap events
            # For now, return a placeholder based on liquidity
            liquidity = await self._get_pair_liquidity_usd(
                pair.token0.address, pair.token1.address, pair.dex
            )
            
            # Estimate volume as 2x liquidity (simplified)
            return liquidity * Decimal("2")
            
        except Exception as e:
            logger.error(f"Error getting pair volume: {e}")
            return Decimal("0")
    
    async def _cleanup_inactive_pairs(self):
        """Remove pairs that haven't been active recently"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=48)  # 48 hour cutoff for Polygon
            
            # Remove pairs with low volume or old data
            active_pairs = []
            for pair in self.active_pairs:
                pair_key = f"{pair.token0.address}-{pair.token1.address}-{pair.address}"
                
                last_updated = self.pair_last_updated.get(pair_key, datetime.min)
                volume = self.pair_volumes.get(pair_key, Decimal("0"))
                
                if last_updated > cutoff_time and volume > self.min_volume_24h_usd:
                    active_pairs.append(pair)
                else:
                    logger.info(f"Removing inactive Polygon pair: {pair.token0.symbol}/{pair.token1.symbol}")
            
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
    
    async def get_token_pairs_by_dex(self, token_address: str) -> Dict[str, List[DexPair]]:
        """Get all pairs for a token grouped by DEX"""
        pairs_by_dex = {}
        
        for pair in self.active_pairs:
            if pair.token0.address == token_address or pair.token1.address == token_address:
                if pair.dex not in pairs_by_dex:
                    pairs_by_dex[pair.dex] = []
                pairs_by_dex[pair.dex].append(pair)
        
        return pairs_by_dex
    
    async def get_high_volume_pairs(self, min_volume_usd: Decimal = None) -> List[DexPair]:
        """Get pairs with high trading volume"""
        if min_volume_usd is None:
            min_volume_usd = self.min_volume_24h_usd
        
        high_volume_pairs = []
        
        for pair in self.active_pairs:
            pair_key = f"{pair.token0.address}-{pair.token1.address}-{pair.address}"
            volume = self.pair_volumes.get(pair_key, Decimal("0"))
            
            if volume >= min_volume_usd:
                high_volume_pairs.append(pair)
        
        # Sort by volume (descending)
        high_volume_pairs.sort(
            key=lambda p: self.pair_volumes.get(
                f"{p.token0.address}-{p.token1.address}-{p.address}", Decimal("0")
            ),
            reverse=True
        )
        
        return high_volume_pairs
    
    def get_stats(self) -> Dict[str, Any]:
        """Get discovery service statistics"""
        total_volume = sum(self.pair_volumes.values())
        avg_volume = total_volume / len(self.pair_volumes) if self.pair_volumes else Decimal("0")
        
        # Group pairs by DEX
        pairs_by_dex = {}
        for pair in self.active_pairs:
            if pair.dex not in pairs_by_dex:
                pairs_by_dex[pair.dex] = 0
            pairs_by_dex[pair.dex] += 1
        
        return {
            "discovered_tokens": len(self.discovered_tokens),
            "active_pairs": len(self.active_pairs),
            "pairs_by_dex": pairs_by_dex,
            "total_volume_24h_usd": float(total_volume),
            "avg_volume_24h_usd": float(avg_volume),
            "last_discovery_run": max(self.pair_last_updated.values()).isoformat() if self.pair_last_updated else None,
            "supported_dexs": list(self.dex_routers.keys()),
            "base_tokens": len(self.base_tokens)
        }
