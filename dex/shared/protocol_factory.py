"""
Protocol Factory for creating network-aware protocol adapters
Centralizes address management and ABI fetching for all DEX protocols
"""
import logging
from typing import Dict, Any, Optional, Type
from decimal import Decimal

from .contract_addresses import get_router_address, get_factory_address, get_base_tokens, get_chain_addresses
from .abi_fetcher import ABIFetcher, FALLBACK_ABIS

logger = logging.getLogger(__name__)

class NetworkAwareProtocolAdapter:
    """Base class for network-aware protocol adapters"""
    
    def __init__(self, chain: str, protocol: str, engine, config):
        self.chain = chain
        self.protocol = protocol
        self.engine = engine
        self.config = config
        
        # Get network-aware addresses
        self.router_address = get_router_address(chain, protocol)
        self.factory_address = get_factory_address(chain, protocol)
        self.base_tokens = get_base_tokens(chain)
        self.chain_addresses = get_chain_addresses(chain)
        
        # ABI fetcher for dynamic contract interaction
        self.abi_fetcher = ABIFetcher()
        
        # Protocol-specific settings
        self.fee_rates = self._get_fee_rates()
        
    def _get_fee_rates(self) -> Dict[str, Decimal]:
        """Get protocol-specific fee rates"""
        fee_mapping = {
            'uniswap_v2': Decimal("0.003"),     # 0.3%
            'uniswap_v3': Decimal("0.0005"),    # 0.05% (variable)
            'sushiswap': Decimal("0.003"),      # 0.3%
            'quickswap': Decimal("0.003"),      # 0.3%
            'pancakeswap_v2': Decimal("0.0025"), # 0.25%
            'pancakeswap_v3': Decimal("0.0005"), # 0.05% (variable)
            'biswap': Decimal("0.001"),         # 0.1%
            'apeswap': Decimal("0.002"),        # 0.2%
            'curve': Decimal("0.0004"),         # 0.04%
        }
        return fee_mapping.get(self.protocol, Decimal("0.003"))
    
    async def initialize(self) -> bool:
        """Initialize the protocol adapter with dynamic ABIs"""
        try:
            # Initialize ABI fetcher
            await self.abi_fetcher.__aenter__()
            
            # Fetch router ABI
            network_name = self.chain_addresses.get('network_name', 'mainnet')
            self.router_abi = await self.abi_fetcher.fetch_abi(
                self.chain, network_name, self.router_address
            )
            
            if not self.router_abi:
                # Use fallback ABI based on protocol type
                if 'v2' in self.protocol or self.protocol in ['quickswap', 'sushiswap', 'pancakeswap_v2']:
                    self.router_abi = FALLBACK_ABIS.get('uniswap_v2_router', [])
                elif 'v3' in self.protocol:
                    self.router_abi = FALLBACK_ABIS.get('uniswap_v3_router', [])
                else:
                    self.router_abi = FALLBACK_ABIS.get('uniswap_v2_router', [])
            
            # Fetch factory ABI
            self.factory_abi = await self.abi_fetcher.fetch_abi(
                self.chain, network_name, self.factory_address
            )
            
            if not self.factory_abi:
                self.factory_abi = FALLBACK_ABIS.get('uniswap_v2_factory', [])
            
            # Create contract instances
            if self.router_abi:
                self.router_contract = self.engine.w3.eth.contract(
                    address=self.engine.w3.to_checksum_address(self.router_address),
                    abi=self.router_abi
                )
            
            if self.factory_abi:
                self.factory_contract = self.engine.w3.eth.contract(
                    address=self.engine.w3.to_checksum_address(self.factory_address),
                    abi=self.factory_abi
                )
            
            logger.info(f"Initialized {self.protocol} adapter for {self.chain} with dynamic ABIs")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.protocol} adapter: {e}")
            return False
    
    async def get_token_price_usd(self, token_address: str) -> Decimal:
        """Get token price in USD using dynamic price fetching"""
        try:
            # Try to get price from major stablecoin pairs
            usdc_address = self.base_tokens.get('USDC')
            usdt_address = self.base_tokens.get('USDT')
            
            # Try USDC first
            if usdc_address and token_address.lower() != usdc_address.lower():
                try:
                    price = await self._get_quote_from_pair(token_address, usdc_address)
                    if price and price > 0:
                        return price
                except Exception:
                    pass
            
            # Try USDT as fallback
            if usdt_address and token_address.lower() != usdt_address.lower():
                try:
                    price = await self._get_quote_from_pair(token_address, usdt_address)
                    if price and price > 0:
                        return price
                except Exception:
                    pass
            
            # Fallback to approximate prices for known tokens
            return self._get_fallback_price(token_address)
            
        except Exception as e:
            logger.error(f"Error getting token price for {token_address}: {e}")
            return Decimal("1")
    
    def _get_fallback_price(self, token_address: str) -> Decimal:
        """Get fallback price for known tokens"""
        # Chain-specific native token prices
        native_prices = {
            'ethereum': Decimal("2500"),  # ETH
            'bsc': Decimal("300"),        # BNB
            'polygon': Decimal("0.8")     # MATIC
        }
        
        # Get addresses for comparison
        token_lower = token_address.lower()
        
        # Check if it's a native token wrapper
        native_tokens = ['WETH', 'WBNB', 'WMATIC']
        for native in native_tokens:
            native_addr = self.base_tokens.get(native, '').lower()
            if token_lower == native_addr:
                return native_prices.get(self.chain, Decimal("1"))
        
        # Check stablecoins
        stablecoins = ['USDC', 'USDT', 'DAI', 'BUSD']
        for stable in stablecoins:
            stable_addr = self.base_tokens.get(stable, '').lower()
            if token_lower == stable_addr:
                return Decimal("1.0")
        
        # Check major tokens
        major_tokens = {
            'WBTC': Decimal("45000"),
            'BTC': Decimal("45000")
        }
        
        for symbol, price in major_tokens.items():
            token_addr = self.base_tokens.get(symbol, '').lower()
            if token_lower == token_addr:
                return price
        
        return Decimal("1")
    
    async def _get_quote_from_pair(self, token_in: str, token_out: str) -> Optional[Decimal]:
        """Get quote from a trading pair - to be implemented by specific adapters"""
        # This is a placeholder - specific adapters should implement this
        return None
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if hasattr(self, 'abi_fetcher'):
                await self.abi_fetcher.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

class ProtocolFactory:
    """Factory for creating network-aware protocol adapters"""
    
    @staticmethod
    def create_adapter(chain: str, protocol: str, engine, config) -> NetworkAwareProtocolAdapter:
        """Create a network-aware protocol adapter"""
        return NetworkAwareProtocolAdapter(chain, protocol, engine, config)
    
    @staticmethod
    def get_supported_protocols(chain: str) -> list:
        """Get list of supported protocols for a chain"""
        protocols = {
            'ethereum': ['uniswap_v2', 'uniswap_v3', 'sushiswap'],
            'bsc': ['pancakeswap_v2', 'pancakeswap_v3', 'biswap', 'apeswap'],
            'polygon': ['quickswap', 'sushiswap', 'uniswap_v3', 'curve']
        }
        return protocols.get(chain, [])
