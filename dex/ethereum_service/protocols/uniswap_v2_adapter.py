import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import json
from web3 import AsyncWeb3
from web3.exceptions import Web3Exception

logger = logging.getLogger(__name__)

class UniswapV2Adapter:
    """Uniswap V2 protocol adapter for price fetching and pool monitoring"""
    
    # Uniswap V2 Factory address (same on mainnet and testnets)
    FACTORY_ADDRESS = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    
    # Uniswap V2 Router address
    ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
    
    # Factory ABI (minimal for pair creation)
    FACTORY_ABI = [
        {
            "constant": True,
            "inputs": [
                {"internalType": "address", "name": "tokenA", "type": "address"},
                {"internalType": "address", "name": "tokenB", "type": "address"}
            ],
            "name": "getPair",
            "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Pair ABI (minimal for reserves)
    PAIR_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "getReserves",
            "outputs": [
                {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
                {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
                {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
            ],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    def __init__(self, w3: AsyncWeb3, factory_address: str = None, router_address: str = None):
        self.w3 = w3
        self.factory_address = factory_address or self.FACTORY_ADDRESS
        self.router_address = router_address or self.ROUTER_ADDRESS
        self.factory_contract = w3.eth.contract(
            address=self.factory_address,
            abi=self.FACTORY_ABI
        )
        self.pair_cache = {}  # Cache pair addresses
        self.price_cache = {}  # Cache latest prices
        
    async def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """Get Uniswap V2 pair address for two tokens"""
        try:
            cache_key = f"{token_a.lower()}-{token_b.lower()}"
            if cache_key in self.pair_cache:
                return self.pair_cache[cache_key]
                
            pair_address = await self.factory_contract.functions.getPair(
                token_a, token_b
            ).call()
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None
                
            self.pair_cache[cache_key] = pair_address
            return pair_address
            
        except Exception as e:
            logger.error(f"Error getting pair address for {token_a}/{token_b}: {e}")
            return None
    
    async def get_pair_reserves(self, pair_address: str) -> Optional[Tuple[int, int, int]]:
        """Get reserves for a Uniswap V2 pair"""
        try:
            pair_contract = self.w3.eth.contract(
                address=pair_address,
                abi=self.PAIR_ABI
            )
            
            reserves = await pair_contract.functions.getReserves().call()
            return reserves[0], reserves[1], reserves[2]  # reserve0, reserve1, timestamp
            
        except Exception as e:
            logger.error(f"Error getting reserves for pair {pair_address}: {e}")
            return None
    
    async def get_token_price(self, token_a: str, token_b: str, amount_in: int = 10**18) -> Optional[Decimal]:
        """Get price of token_a in terms of token_b from Uniswap V2 pool"""
        try:
            pair_address = await self.get_pair_address(token_a, token_b)
            if not pair_address:
                return None
                
            reserves = await self.get_pair_reserves(pair_address)
            if not reserves:
                return None
                
            reserve0, reserve1, _ = reserves
            
            # Get token order in pair
            pair_contract = self.w3.eth.contract(address=pair_address, abi=self.PAIR_ABI)
            token0 = await pair_contract.functions.token0().call()
            
            # Calculate price based on token order
            if token0.lower() == token_a.lower():
                # token_a is token0, token_b is token1
                if reserve0 == 0:
                    return None
                price = Decimal(reserve1) / Decimal(reserve0)
            else:
                # token_a is token1, token_b is token0
                if reserve1 == 0:
                    return None
                price = Decimal(reserve0) / Decimal(reserve1)
                
            return price
            
        except Exception as e:
            logger.error(f"Error getting price for {token_a}/{token_b}: {e}")
            return None
    
    async def get_multiple_prices(self, token_pairs: List[Tuple[str, str]]) -> Dict[str, Decimal]:
        """Get prices for multiple token pairs efficiently"""
        tasks = []
        for token_a, token_b in token_pairs:
            task = self.get_token_price(token_a, token_b)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        prices = {}
        for i, result in enumerate(results):
            if not isinstance(result, Exception) and result is not None:
                token_a, token_b = token_pairs[i]
                prices[f"{token_a}/{token_b}"] = result
                
        return prices
    
    async def get_pool_liquidity(self, token_a: str, token_b: str) -> Optional[Tuple[Decimal, Decimal]]:
        """Get pool liquidity for a pair"""
        try:
            pair_address = await self.get_pair_address(token_a, token_b)
            if not pair_address:
                return None
                
            reserves = await self.get_pair_reserves(pair_address)
            if not reserves:
                return None
                
            reserve0, reserve1, _ = reserves
            return Decimal(reserve0), Decimal(reserve1)
            
        except Exception as e:
            logger.error(f"Error getting liquidity for {token_a}/{token_b}: {e}")
            return None
    
    def calculate_amount_out(self, amount_in: int, reserve_in: int, reserve_out: int) -> int:
        """Calculate output amount using Uniswap V2 formula with 0.3% fee"""
        if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
            return 0
            
        # Apply 0.3% fee
        amount_in_with_fee = amount_in * 997
        numerator = amount_in_with_fee * reserve_out
        denominator = (reserve_in * 1000) + amount_in_with_fee
        
        return numerator // denominator
    
    def calculate_amount_in(self, amount_out: int, reserve_in: int, reserve_out: int) -> int:
        """Calculate input amount needed for desired output amount"""
        if amount_out <= 0 or reserve_in <= 0 or reserve_out <= 0:
            return 0
            
        if amount_out >= reserve_out:
            return 0  # Not enough liquidity
            
        numerator = reserve_in * amount_out * 1000
        denominator = (reserve_out - amount_out) * 997
        
        return (numerator // denominator) + 1