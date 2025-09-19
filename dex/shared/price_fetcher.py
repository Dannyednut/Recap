"""
Dynamic price fetching utility for multi-chain token prices
Integrates with DEX contracts to get real-time pricing data
"""
import logging
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from web3 import AsyncWeb3
from web3.contract import AsyncContract

from .contract_addresses import get_base_tokens, get_router_address, get_factory_address
from .abi_fetcher import ABIFetcher, FALLBACK_ABIS

logger = logging.getLogger(__name__)

class MultiChainPriceFetcher:
    """Fetches token prices across multiple chains and DEXes"""
    
    def __init__(self):
        self.abi_fetcher = ABIFetcher()
        self.price_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    async def initialize(self):
        """Initialize the price fetcher"""
        await self.abi_fetcher.__aenter__()
        
    async def get_token_price_usd(self, chain: str, token_address: str, engine) -> Decimal:
        """Get token price in USD for any supported chain"""
        cache_key = f"{chain}:{token_address.lower()}"
        
        # Check cache first
        if cache_key in self.price_cache:
            price_data = self.price_cache[cache_key]
            if asyncio.get_event_loop().time() - price_data['timestamp'] < self.cache_ttl:
                return price_data['price']
        
        try:
            price = await self._fetch_token_price(chain, token_address, engine)
            
            # Cache the result
            self.price_cache[cache_key] = {
                'price': price,
                'timestamp': asyncio.get_event_loop().time()
            }
            
            return price
            
        except Exception as e:
            logger.error(f"Error fetching price for {token_address} on {chain}: {e}")
            return self._get_fallback_price(chain, token_address)
    
    async def _fetch_token_price(self, chain: str, token_address: str, engine) -> Decimal:
        """Fetch token price from DEX contracts"""
        base_tokens = get_base_tokens(chain)
        
        # Try to get price against major stablecoins
        stablecoins = ['USDC', 'USDT', 'DAI', 'BUSD']
        
        for stable_symbol in stablecoins:
            stable_address = base_tokens.get(stable_symbol)
            if not stable_address or token_address.lower() == stable_address.lower():
                continue
                
            try:
                price = await self._get_pair_price(
                    chain, token_address, stable_address, engine
                )
                if price and price > 0:
                    return price
            except Exception as e:
                logger.debug(f"Failed to get price against {stable_symbol}: {e}")
                continue
        
        # If no stablecoin pair found, try native token
        native_tokens = ['WETH', 'WBNB', 'WMATIC']
        for native_symbol in native_tokens:
            native_address = base_tokens.get(native_symbol)
            if not native_address or token_address.lower() == native_address.lower():
                continue
                
            try:
                # Get token price in native token
                native_price = await self._get_pair_price(
                    chain, token_address, native_address, engine
                )
                if native_price and native_price > 0:
                    # Convert to USD using native token price
                    native_usd_price = self._get_native_token_price_usd(chain)
                    return native_price * native_usd_price
            except Exception as e:
                logger.debug(f"Failed to get price against {native_symbol}: {e}")
                continue
        
        # Fallback to hardcoded prices
        return self._get_fallback_price(chain, token_address)
    
    async def _get_pair_price(self, chain: str, token_in: str, token_out: str, engine) -> Optional[Decimal]:
        """Get price between two tokens using DEX contracts"""
        try:
            # Try multiple DEXes for the chain
            protocols = self._get_chain_protocols(chain)
            
            for protocol in protocols:
                try:
                    price = await self._get_protocol_price(
                        chain, protocol, token_in, token_out, engine
                    )
                    if price and price > 0:
                        return price
                except Exception as e:
                    logger.debug(f"Failed to get price from {protocol}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting pair price: {e}")
            return None
    
    async def _get_protocol_price(self, chain: str, protocol: str, token_in: str, token_out: str, engine) -> Optional[Decimal]:
        """Get price from a specific protocol"""
        try:
            router_address = get_router_address(chain, protocol)
            if not router_address:
                return None
            
            # Get router ABI
            network_name = 'mainnet'  # TODO: Get from config
            router_abi = await self.abi_fetcher.fetch_abi(chain, network_name, router_address)
            
            if not router_abi:
                # Use fallback ABI
                if 'v3' in protocol:
                    router_abi = FALLBACK_ABIS.get('uniswap_v3_router', [])
                else:
                    router_abi = FALLBACK_ABIS.get('uniswap_v2_router', [])
            
            if not router_abi:
                return None
            
            # Create router contract
            router_contract = engine.w3.eth.contract(
                address=engine.w3.to_checksum_address(router_address),
                abi=router_abi
            )
            
            # Get quote for 1 token (adjusted for decimals)
            amount_in = Decimal("1000000000000000000")  # 1 token with 18 decimals
            
            if 'v3' in protocol:
                # For V3, we need to use quoter contract
                return await self._get_v3_quote(chain, protocol, token_in, token_out, amount_in, engine)
            else:
                # For V2, use getAmountsOut
                path = [
                    engine.w3.to_checksum_address(token_in),
                    engine.w3.to_checksum_address(token_out)
                ]
                
                amounts_out = await router_contract.functions.getAmountsOut(
                    int(amount_in), path
                ).call()
                
                if len(amounts_out) >= 2 and amounts_out[1] > 0:
                    # Calculate price (adjust for token decimals)
                    price = Decimal(amounts_out[1]) / amount_in
                    return price
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting {protocol} price: {e}")
            return None
    
    async def _get_v3_quote(self, chain: str, protocol: str, token_in: str, token_out: str, amount_in: Decimal, engine) -> Optional[Decimal]:
        """Get quote from Uniswap V3 style quoter"""
        try:
            # Get quoter address (protocol specific)
            quoter_addresses = {
                'uniswap_v3': {
                    'ethereum': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
                    'polygon': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
                },
                'pancakeswap_v3': {
                    'bsc': '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997'
                }
            }
            
            quoter_address = quoter_addresses.get(protocol, {}).get(chain)
            if not quoter_address:
                return None
            
            # Get quoter ABI
            network_name = 'mainnet'  # TODO: Get from config
            quoter_abi = await self.abi_fetcher.fetch_abi(chain, network_name, quoter_address)
            
            if not quoter_abi:
                quoter_abi = FALLBACK_ABIS.get('uniswap_v3_quoter', [])
            
            if not quoter_abi:
                return None
            
            # Create quoter contract
            quoter_contract = engine.w3.eth.contract(
                address=engine.w3.to_checksum_address(quoter_address),
                abi=quoter_abi
            )
            
            # Get quote with 0.3% fee tier (most common)
            fee = 3000
            amount_out = await quoter_contract.functions.quoteExactInputSingle(
                engine.w3.to_checksum_address(token_in),
                engine.w3.to_checksum_address(token_out),
                fee,
                int(amount_in),
                0  # sqrtPriceLimitX96
            ).call()
            
            if amount_out > 0:
                price = Decimal(amount_out) / amount_in
                return price
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting V3 quote: {e}")
            return None
    
    def _get_chain_protocols(self, chain: str) -> List[str]:
        """Get supported protocols for a chain"""
        protocols = {
            'ethereum': ['uniswap_v2', 'uniswap_v3', 'sushiswap'],
            'bsc': ['pancakeswap_v2', 'pancakeswap_v3', 'biswap'],
            'polygon': ['quickswap', 'sushiswap', 'uniswap_v3']
        }
        return protocols.get(chain, [])
    
    async def _get_native_token_price_usd(self, chain: str, engine=None) -> Decimal:
        """Get native token price in USD using real DEX data"""
        try:
            if not engine:
                return self._get_fallback_native_price(chain)
            
            base_tokens = get_base_tokens(chain)
            native_token_map = {
                'ethereum': 'WETH',
                'bsc': 'WBNB', 
                'polygon': 'WMATIC'
            }
            
            native_symbol = native_token_map.get(chain)
            if not native_symbol:
                return self._get_fallback_native_price(chain)
            
            native_address = base_tokens.get(native_symbol)
            if not native_address:
                return self._get_fallback_native_price(chain)
            
            # Try to get price against USDC first, then USDT
            for stable_symbol in ['USDC', 'USDT']:
                stable_address = base_tokens.get(stable_symbol)
                if stable_address and stable_address.lower() != native_address.lower():
                    price = await self._get_pair_price(chain, native_address, stable_address, engine)
                    if price and price > 0:
                        return price
            
            # Fallback to hardcoded prices if DEX calls fail
            return self._get_fallback_native_price(chain)
            
        except Exception as e:
            logger.debug(f"Error getting native token price for {chain}: {e}")
            return self._get_fallback_native_price(chain)
    
    def _get_fallback_native_price(self, chain: str) -> Decimal:
        """Fallback native token prices"""
        prices = {
            'ethereum': Decimal("3200"),  # ETH
            'bsc': Decimal("600"),        # BNB  
            'polygon': Decimal("0.85")    # MATIC
        }
        return prices.get(chain, Decimal("1"))
    
    def _get_chain_protocols(self, chain: str) -> List[str]:
        """Get supported protocols for a chain"""
        protocols = {
            'ethereum': ['uniswap_v2', 'uniswap_v3', 'sushiswap'],
            'bsc': ['pancakeswap_v2', 'pancakeswap_v3', 'biswap'],
            'polygon': ['quickswap', 'sushiswap', 'uniswap_v3']
        }
        return protocols.get(chain, [])
    
    def _get_fallback_price(self, chain: str, token_address: str) -> Decimal:
        """Get fallback price for known tokens with updated realistic prices"""
        base_tokens = get_base_tokens(chain)
        token_lower = token_address.lower()
        
        # Check native tokens with current market prices
        native_prices = {
            'ethereum': Decimal("3200"),  # ETH current price
            'bsc': Decimal("600"),        # BNB current price
            'polygon': Decimal("0.85")    # MATIC current price
        }
        
        native_tokens = ['WETH', 'WBNB', 'WMATIC']
        for symbol in native_tokens:
            address = base_tokens.get(symbol, '').lower()
            if address == token_lower:
                chain_name = {
                    'WETH': 'ethereum',
                    'WBNB': 'bsc', 
                    'WMATIC': 'polygon'
                }.get(symbol, chain)
                return native_prices.get(chain_name, Decimal("1"))
        
        # Check stablecoins
        stablecoins = ['USDC', 'USDT', 'DAI', 'BUSD']
        for symbol in stablecoins:
            address = base_tokens.get(symbol, '').lower()
            if address == token_lower:
                return Decimal("1.00")
        
        # Check major tokens with current market prices
        major_tokens = {
            'WBTC': Decimal("67000"),  # BTC current price
            'BTC': Decimal("67000"),
            'LINK': Decimal("15"),     # LINK current price
            'UNI': Decimal("8"),       # UNI current price
            'AAVE': Decimal("85"),     # AAVE current price
            'COMP': Decimal("55"),     # COMP current price
            'MKR': Decimal("1200"),    # MKR current price
            'SNX': Decimal("2.5"),     # SNX current price
            'CRV': Decimal("0.35"),    # CRV current price
            'BAL': Decimal("2.8"),     # BAL current price
            'YFI': Decimal("6500"),    # YFI current price
            'SUSHI': Decimal("0.85")   # SUSHI current price
        }
        
        for symbol, price in major_tokens.items():
            address = base_tokens.get(symbol, '').lower()
            if address == token_lower:
                return price
        
        # Default fallback for unknown tokens
        return Decimal("1.00")

    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self.abi_fetcher.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
