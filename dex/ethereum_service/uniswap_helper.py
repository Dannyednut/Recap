import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from web3 import Web3
from eth_abi import encode, decode

logger = logging.getLogger(__name__)

class UniswapHelper:
    """Helper class for real Uniswap contract interactions"""
    
    # Uniswap V2 Factory ABI (minimal)
    FACTORY_V2_ABI = [
        {
            "constant": True,
            "inputs": [
                {"name": "tokenA", "type": "address"},
                {"name": "tokenB", "type": "address"}
            ],
            "name": "getPair",
            "outputs": [{"name": "pair", "type": "address"}],
            "type": "function"
        }
    ]
    
    # Uniswap V2 Pair ABI (minimal)
    PAIR_V2_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "getReserves",
            "outputs": [
                {"name": "reserve0", "type": "uint112"},
                {"name": "reserve1", "type": "uint112"},
                {"name": "blockTimestampLast", "type": "uint32"}
            ],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        }
    ]
    
    # Uniswap V3 Factory ABI (minimal)
    FACTORY_V3_ABI = [
        {
            "inputs": [
                {"name": "tokenA", "type": "address"},
                {"name": "tokenB", "type": "address"},
                {"name": "fee", "type": "uint24"}
            ],
            "name": "getPool",
            "outputs": [{"name": "pool", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Uniswap V3 Pool ABI (minimal)
    POOL_V3_ABI = [
        {
            "inputs": [],
            "name": "slot0",
            "outputs": [
                {"name": "sqrtPriceX96", "type": "uint160"},
                {"name": "tick", "type": "int24"},
                {"name": "observationIndex", "type": "uint16"},
                {"name": "observationCardinality", "type": "uint16"},
                {"name": "observationCardinalityNext", "type": "uint16"},
                {"name": "feeProtocol", "type": "uint8"},
                {"name": "unlocked", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "liquidity",
            "outputs": [{"name": "", "type": "uint128"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    def __init__(self, w3, factory_v2_address: str, factory_v3_address: str):
        self.w3 = w3
        self.factory_v2_address = factory_v2_address
        self.factory_v3_address = factory_v3_address
        
        # Initialize contracts
        self.factory_v2 = w3.eth.contract(
            address=Web3.to_checksum_address(factory_v2_address),
            abi=self.FACTORY_V2_ABI
        )
        self.factory_v3 = w3.eth.contract(
            address=Web3.to_checksum_address(factory_v3_address),
            abi=self.FACTORY_V3_ABI
        )
    
    async def get_v2_pair_reserves(self, token_a: str, token_b: str) -> Optional[Tuple[Decimal, Decimal]]:
        """Get actual V2 pair reserves from blockchain"""
        try:
            # Get pair address
            pair_address = await self.factory_v2.functions.getPair(
                Web3.to_checksum_address(token_a),
                Web3.to_checksum_address(token_b)
            ).call()
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None
            
            # Get pair contract
            pair_contract = self.w3.eth.contract(
                address=pair_address,
                abi=self.PAIR_V2_ABI
            )
            
            # Get reserves
            reserves = await pair_contract.functions.getReserves().call()
            reserve0, reserve1, _ = reserves
            
            # Get token order
            token0 = await pair_contract.functions.token0().call()
            
            # Ensure correct order (token_a, token_b)
            if token0.lower() == token_a.lower():
                return (Decimal(str(reserve0)), Decimal(str(reserve1)))
            else:
                return (Decimal(str(reserve1)), Decimal(str(reserve0)))
                
        except Exception as e:
            logger.error(f"Error getting V2 reserves for {token_a}/{token_b}: {e}")
            return None
    
    async def get_v3_pool_data(self, token_a: str, token_b: str, fee_tier: int) -> Optional[Dict]:
        """Get actual V3 pool data from blockchain"""
        try:
            # Get pool address
            pool_address = await self.factory_v3.functions.getPool(
                Web3.to_checksum_address(token_a),
                Web3.to_checksum_address(token_b),
                fee_tier
            ).call()
            
            if pool_address == "0x0000000000000000000000000000000000000000":
                return None
            
            # Get pool contract
            pool_contract = self.w3.eth.contract(
                address=pool_address,
                abi=self.POOL_V3_ABI
            )
            
            # Get slot0 data
            slot0 = await pool_contract.functions.slot0().call()
            sqrt_price_x96, tick, _, _, _, _, _ = slot0
            
            # Get liquidity
            liquidity = await pool_contract.functions.liquidity().call()
            
            return {
                "pool_address": pool_address,
                "sqrtPriceX96": sqrt_price_x96,
                "tick": tick,
                "liquidity": liquidity,
                "fee": fee_tier
            }
            
        except Exception as e:
            logger.error(f"Error getting V3 pool data for {token_a}/{token_b}: {e}")
            return None
    
    def calculate_v2_price(self, reserve_a: Decimal, reserve_b: Decimal) -> Decimal:
        """Calculate V2 price from reserves"""
        if reserve_a == 0:
            return Decimal("0")
        return reserve_b / reserve_a
    
    def calculate_v2_amount_out(self, amount_in: Decimal, reserve_in: Decimal, reserve_out: Decimal) -> Decimal:
        """Calculate V2 amount out using the constant product formula"""
        try:
            if reserve_in == 0 or reserve_out == 0:
                return Decimal("0")
            
            # Uniswap V2 formula with 0.3% fee
            amount_in_with_fee = amount_in * 997
            numerator = amount_in_with_fee * reserve_out
            denominator = reserve_in * 1000 + amount_in_with_fee
            
            return numerator / denominator
            
        except Exception as e:
            logger.error(f"Error calculating V2 amount out: {e}")
            return Decimal("0")
    
    def sqrt_price_to_price(self, sqrt_price_x96: int, decimals_a: int = 18, decimals_b: int = 18) -> Decimal:
        """Convert V3 sqrtPriceX96 to actual price"""
        try:
            # Calculate price from sqrt price
            sqrt_price = Decimal(str(sqrt_price_x96)) / Decimal(str(2 ** 96))
            price = sqrt_price ** 2
            
            # Adjust for decimals
            decimal_adjustment = Decimal(str(10 ** (decimals_b - decimals_a)))
            adjusted_price = price * decimal_adjustment
            
            return adjusted_price
            
        except Exception as e:
            logger.error(f"Error converting sqrt price: {e}")
            return Decimal("0")
    
    async def get_best_v3_fee_tier(self, token_a: str, token_b: str) -> int:
        """Find the V3 fee tier with the most liquidity"""
        try:
            fee_tiers = [100, 500, 3000, 10000]  # 0.01%, 0.05%, 0.3%, 1%
            best_tier = 3000
            best_liquidity = 0
            
            for fee_tier in fee_tiers:
                pool_data = await self.get_v3_pool_data(token_a, token_b, fee_tier)
                if pool_data and pool_data["liquidity"] > best_liquidity:
                    best_liquidity = pool_data["liquidity"]
                    best_tier = fee_tier
            
            return best_tier
            
        except Exception as e:
            logger.error(f"Error finding best V3 fee tier: {e}")
            return 3000  # Default to 0.3%