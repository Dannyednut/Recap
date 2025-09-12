import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import math
from web3 import AsyncWeb3

logger = logging.getLogger(__name__)

class UniswapV3Adapter:
    """Uniswap V3 protocol adapter for price fetching and pool monitoring"""
    
    # Uniswap V3 Factory address
    FACTORY_ADDRESS = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    
    # Uniswap V3 Quoter address
    QUOTER_ADDRESS = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
    
    # Factory ABI (minimal)
    FACTORY_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "tokenA", "type": "address"},
                {"internalType": "address", "name": "tokenB", "type": "address"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"}
            ],
            "name": "getPool",
            "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Pool ABI (minimal)
    POOL_ABI = [
        {
            "inputs": [],
            "name": "slot0",
            "outputs": [
                {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                {"internalType": "bool", "name": "unlocked", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "liquidity",
            "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "token0",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "token1",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Quoter ABI (for precise quotes)
    QUOTER_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "tokenIn", "type": "address"},
                {"internalType": "address", "name": "tokenOut", "type": "address"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"},
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
            ],
            "name": "quoteExactInputSingle",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    
    # Common fee tiers in Uniswap V3
    FEE_TIERS = [500, 3000, 10000]  # 0.05%, 0.3%, 1%
    
    def __init__(self, w3: AsyncWeb3):
        self.w3 = w3
        self.factory_contract = w3.eth.contract(
            address=self.FACTORY_ADDRESS,
            abi=self.FACTORY_ABI
        )
        self.quoter_contract = w3.eth.contract(
            address=self.QUOTER_ADDRESS,
            abi=self.QUOTER_ABI
        )
        self.pool_cache = {}  # Cache pool addresses
        self.price_cache = {}  # Cache latest prices
    
    async def get_pool_address(self, token_a: str, token_b: str, fee: int) -> Optional[str]:
        """Get Uniswap V3 pool address for two tokens and fee tier"""
        try:
            cache_key = f"{token_a.lower()}-{token_b.lower()}-{fee}"
            if cache_key in self.pool_cache:
                return self.pool_cache[cache_key]
                
            pool_address = await self.factory_contract.functions.getPool(
                token_a, token_b, fee
            ).call()
            
            if pool_address == "0x0000000000000000000000000000000000000000":
                return None
                
            self.pool_cache[cache_key] = pool_address
            return pool_address
            
        except Exception as e:
            logger.error(f"Error getting pool address for {token_a}/{token_b} fee {fee}: {e}")
            return None
    
    async def get_pool_slot0(self, pool_address: str) -> Optional[Tuple[int, int]]:
        """Get slot0 data (sqrt price and tick) from pool"""
        try:
            pool_contract = self.w3.eth.contract(
                address=pool_address,
                abi=self.POOL_ABI
            )
            
            slot0 = await pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            tick = slot0[1]
            
            return sqrt_price_x96, tick
            
        except Exception as e:
            logger.error(f"Error getting slot0 for pool {pool_address}: {e}")
            return None
    
    def sqrt_price_to_price(self, sqrt_price_x96: int, decimals_token0: int = 18, decimals_token1: int = 18) -> Decimal:
        """Convert sqrt price X96 to human readable price"""
        try:
            # Remove the X96 scaling
            sqrt_price = sqrt_price_x96 / (2 ** 96)
            
            # Square to get the actual price
            price = sqrt_price ** 2
            
            # Adjust for token decimals
            decimal_adjustment = 10 ** (decimals_token1 - decimals_token0)
            adjusted_price = price * decimal_adjustment
            
            return Decimal(str(adjusted_price))
            
        except Exception as e:
            logger.error(f"Error converting sqrt price: {e}")
            return Decimal("0")
    
    async def get_token_price(self, token_a: str, token_b: str, fee: Optional[int] = None) -> Optional[Decimal]:
        """Get price of token_a in terms of token_b from Uniswap V3 pool"""
        try:
            # Try different fee tiers if none specified
            fee_tiers = [fee] if fee else self.FEE_TIERS
            
            for fee_tier in fee_tiers:
                pool_address = await self.get_pool_address(token_a, token_b, fee_tier)
                if not pool_address:
                    continue
                    
                slot0_data = await self.get_pool_slot0(pool_address)
                if not slot0_data:
                    continue
                    
                sqrt_price_x96, _ = slot0_data
                
                # Get token order in pool
                pool_contract = self.w3.eth.contract(address=pool_address, abi=self.POOL_ABI)
                token0 = await pool_contract.functions.token0().call()
                
                # Convert sqrt price to actual price
                price = self.sqrt_price_to_price(sqrt_price_x96)
                
                # Adjust price based on token order
                if token0.lower() != token_a.lower():
                    price = Decimal("1") / price if price > 0 else Decimal("0")
                    
                return price
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting price for {token_a}/{token_b}: {e}")
            return None
    
    async def get_quote(self, token_in: str, token_out: str, amount_in: int, fee: int) -> Optional[int]:
        """Get exact quote for swap using Quoter contract"""
        try:
            amount_out = await self.quoter_contract.functions.quoteExactInputSingle(
                token_in,
                token_out, 
                fee,
                amount_in,
                0  # No price limit
            ).call()
            
            return amount_out
            
        except Exception as e:
            logger.error(f"Error getting quote for {token_in}/{token_out}: {e}")
            return None
    
    async def get_best_pool(self, token_a: str, token_b: str) -> Optional[Tuple[str, int, Decimal]]:
        """Find the pool with best liquidity for a token pair"""
        best_pool = None
        best_fee = None
        best_liquidity = Decimal("0")
        
        for fee in self.FEE_TIERS:
            pool_address = await self.get_pool_address(token_a, token_b, fee)
            if not pool_address:
                continue
                
            try:
                pool_contract = self.w3.eth.contract(address=pool_address, abi=self.POOL_ABI)
                liquidity = await pool_contract.functions.liquidity().call()
                
                if liquidity > best_liquidity:
                    best_liquidity = Decimal(liquidity)
                    best_pool = pool_address
                    best_fee = fee
                    
            except Exception as e:
                logger.error(f"Error getting liquidity for pool {pool_address}: {e}")
                continue
        
        if best_pool:
            return best_pool, best_fee, best_liquidity
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