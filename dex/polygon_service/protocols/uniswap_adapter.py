import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal

# Import shared models
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from dex.shared.models.arbitrage_models import Token, DexPair, SwapQuote

from .base_adapter import BaseProtocolAdapter

logger = logging.getLogger(__name__)

class UniswapV3PolygonAdapter(BaseProtocolAdapter):
    """Uniswap V3 protocol adapter for Polygon"""
    
    def __init__(self, engine, config):
        super().__init__(engine, config)
        self.protocol_name = "Uniswap V3"
        self.router_address = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
        self.factory_address = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
        self.quoter_address = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
        self.fee_rate = Decimal("0.0005")  # 0.05% (can vary by pool)
        
        # V3 uses different fee tiers
        self.fee_tiers = [500, 3000, 10000]  # 0.05%, 0.3%, 1%
        
        self.quoter_abi = [
            {"inputs": [{"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"}, 
                       {"name": "fee", "type": "uint24"}, {"name": "amountIn", "type": "uint256"}, 
                       {"name": "sqrtPriceLimitX96", "type": "uint160"}], 
             "name": "quoteExactInputSingle", "outputs": [{"name": "amountOut", "type": "uint256"}], "type": "function"}
        ]
        
        self.factory_abi = [
            {"inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}, {"name": "fee", "type": "uint24"}], 
             "name": "getPool", "outputs": [{"name": "pool", "type": "address"}], "type": "function"}
        ]
    
    async def get_pair_address(self, token0: str, token1: str) -> Optional[str]:
        """Get pool address for two tokens (V3 uses pools, not pairs)"""
        try:
            # V3 has multiple pools per token pair with different fees
            # Return the most liquid pool (simplified implementation)
            for fee in self.fee_tiers:
                pool_address = await self._get_pool_address(token0, token1, fee)
                if pool_address and pool_address != "0x0000000000000000000000000000000000000000":
                    return pool_address
            return None
            
        except Exception as e:
            logger.error(f"Error getting Uniswap V3 pool address: {e}")
            return None
    
    async def _get_pool_address(self, token0: str, token1: str, fee: int) -> Optional[str]:
        """Get pool address for specific fee tier"""
        try:
            factory_contract = self.engine.w3.eth.contract(
                address=self.factory_address, 
                abi=self.factory_abi
            )
            
            pool_address = await factory_contract.functions.getPool(token0, token1, fee).call()
            return pool_address if pool_address != "0x0000000000000000000000000000000000000000" else None
            
        except Exception as e:
            logger.error(f"Error getting V3 pool address: {e}")
            return None
    
    async def get_reserves(self, pool_address: str) -> Tuple[Decimal, Decimal]:
        """Get liquidity for a V3 pool (different from V2 reserves)"""
        try:
            # V3 pools don't have simple reserves like V2
            # This would require more complex liquidity calculations
            # For now, return placeholder values
            return Decimal("1000000000000000000000"), Decimal("1000000000000000000000")
            
        except Exception as e:
            logger.error(f"Error getting Uniswap V3 liquidity: {e}")
            return Decimal("0"), Decimal("0")
    
    async def get_quote(self, amount_in: Decimal, token_in: str, token_out: str) -> SwapQuote:
        """Get quote for a V3 swap"""
        try:
            quoter_contract = self.engine.w3.eth.contract(
                address=self.quoter_address, 
                abi=self.quoter_abi
            )
            
            best_amount_out = Decimal("0")
            best_fee = 3000  # Default to 0.3%
            
            # Try different fee tiers to find best quote
            for fee in self.fee_tiers:
                try:
                    amount_out = await quoter_contract.functions.quoteExactInputSingle(
                        token_in, token_out, fee, int(amount_in), 0
                    ).call()
                    
                    if Decimal(amount_out) > best_amount_out:
                        best_amount_out = Decimal(amount_out)
                        best_fee = fee
                        
                except Exception:
                    continue
            
            # Calculate price impact (simplified)
            price_impact = await self.get_price_impact(amount_in, token_in, token_out)
            
            # Calculate gas cost
            gas_cost = await self._estimate_swap_gas_cost()
            
            return SwapQuote(
                amount_in=amount_in,
                amount_out=best_amount_out,
                price_impact=price_impact,
                gas_cost=gas_cost,
                protocol=self.protocol_name,
                route=[token_in, token_out]
            )
            
        except Exception as e:
            logger.error(f"Error getting Uniswap V3 quote: {e}")
            return SwapQuote(
                amount_in=amount_in,
                amount_out=Decimal("0"),
                price_impact=Decimal("100"),
                gas_cost=Decimal("0"),
                protocol=self.protocol_name,
                route=[token_in, token_out]
            )
    
    async def execute_swap(self, amount_in: Decimal, min_amount_out: Decimal, 
                          token_in: str, token_out: str, to_address: str) -> Dict[str, Any]:
        """Execute a V3 swap transaction"""
        try:
            # V3 swap execution is more complex than V2
            # This is a simplified implementation placeholder
            return {
                "success": False,
                "error": "V3 swap execution not fully implemented",
                "protocol": self.protocol_name
            }
            
        except Exception as e:
            logger.error(f"Error executing Uniswap V3 swap: {e}")
            return {
                "success": False,
                "error": str(e),
                "protocol": self.protocol_name
            }
    
    async def get_liquidity_info(self, token0: str, token1: str) -> Dict[str, Any]:
        """Get liquidity information for a token pair"""
        try:
            # V3 liquidity calculation is more complex
            # This is a simplified implementation
            total_liquidity = Decimal("0")
            
            for fee in self.fee_tiers:
                pool_address = await self._get_pool_address(token0, token1, fee)
                if pool_address:
                    # Would calculate actual liquidity here
                    total_liquidity += Decimal("100000")  # Placeholder
            
            return {
                "total_liquidity_usd": float(total_liquidity),
                "fee_tiers": self.fee_tiers,
                "volume_24h": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting Uniswap V3 liquidity info: {e}")
            return {"total_liquidity_usd": 0, "volume_24h": 0}
    
    async def _estimate_swap_gas_cost(self) -> Decimal:
        """Estimate gas cost for a V3 swap"""
        try:
            gas_price = await self.engine.w3.eth.gas_price
            gas_limit = 200000  # V3 swaps typically use more gas
            
            # Get MATIC price in USD
            matic_price_usd = Decimal("0.8")  # Simplified
            
            gas_cost_matic = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_matic * matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating V3 gas cost: {e}")
            return Decimal("0.8")  # Default $0.8 estimate


class CurvePolygonAdapter(BaseProtocolAdapter):
    """Curve protocol adapter for Polygon"""
    
    def __init__(self, engine, config):
        super().__init__(engine, config)
        self.protocol_name = "Curve"
        self.router_address = "0x445FE580eF8d70FF569aB36e80c647af338db351"
        self.factory_address = "0x722272D36ef0Da72FF51c5A65Db7b870E2e8D4ee"
        self.fee_rate = Decimal("0.0004")  # 0.04% typical
        
        # Curve pools are different from Uniswap-style pairs
        self.stable_pools = {
            "3pool": "0x445FE580eF8d70FF569aB36e80c647af338db351",  # DAI/USDC/USDT
            "aave": "0x445FE580eF8d70FF569aB36e80c647af338db351"    # aDAI/aUSDC/aUSDT
        }
    
    async def get_pair_address(self, token0: str, token1: str) -> Optional[str]:
        """Get pool address for two tokens (Curve uses pools)"""
        try:
            # Curve pools are typically for stablecoins
            # This is a simplified implementation
            stablecoin_addresses = {
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"   # USDT
            }
            
            if token0 in stablecoin_addresses and token1 in stablecoin_addresses:
                return self.stable_pools["3pool"]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting Curve pool address: {e}")
            return None
    
    async def get_reserves(self, pool_address: str) -> Tuple[Decimal, Decimal]:
        """Get balances for a Curve pool"""
        try:
            # Curve pools have different balance structures
            # This is a simplified implementation
            return Decimal("1000000000000000000000"), Decimal("1000000000000000000000")
            
        except Exception as e:
            logger.error(f"Error getting Curve pool balances: {e}")
            return Decimal("0"), Decimal("0")
    
    async def get_quote(self, amount_in: Decimal, token_in: str, token_out: str) -> SwapQuote:
        """Get quote for a Curve swap"""
        try:
            # Curve swaps are optimized for stablecoins with minimal slippage
            # Simplified implementation assuming 1:1 ratio for stablecoins
            
            stablecoin_addresses = {
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"   # USDT
            }
            
            if token_in in stablecoin_addresses and token_out in stablecoin_addresses:
                # Minimal slippage for stablecoin swaps
                amount_out = amount_in * Decimal("0.9996")  # 0.04% fee
                price_impact = Decimal("0.1")  # Very low price impact
            else:
                amount_out = Decimal("0")
                price_impact = Decimal("100")
            
            gas_cost = await self._estimate_swap_gas_cost()
            
            return SwapQuote(
                amount_in=amount_in,
                amount_out=amount_out,
                price_impact=price_impact,
                gas_cost=gas_cost,
                protocol=self.protocol_name,
                route=[token_in, token_out]
            )
            
        except Exception as e:
            logger.error(f"Error getting Curve quote: {e}")
            return SwapQuote(
                amount_in=amount_in,
                amount_out=Decimal("0"),
                price_impact=Decimal("100"),
                gas_cost=Decimal("0"),
                protocol=self.protocol_name,
                route=[token_in, token_out]
            )
    
    async def execute_swap(self, amount_in: Decimal, min_amount_out: Decimal, 
                          token_in: str, token_out: str, to_address: str) -> Dict[str, Any]:
        """Execute a Curve swap transaction"""
        try:
            # Curve swap execution is specialized for stablecoin pools
            # This is a simplified implementation placeholder
            return {
                "success": False,
                "error": "Curve swap execution not fully implemented",
                "protocol": self.protocol_name
            }
            
        except Exception as e:
            logger.error(f"Error executing Curve swap: {e}")
            return {
                "success": False,
                "error": str(e),
                "protocol": self.protocol_name
            }
    
    async def get_liquidity_info(self, token0: str, token1: str) -> Dict[str, Any]:
        """Get liquidity information for a token pair"""
        try:
            # Curve pools typically have high liquidity for stablecoins
            stablecoin_addresses = {
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"   # USDT
            }
            
            if token0 in stablecoin_addresses and token1 in stablecoin_addresses:
                liquidity_usd = 50000000  # $50M typical for major Curve pools
            else:
                liquidity_usd = 0
            
            return {
                "liquidity_usd": liquidity_usd,
                "volume_24h": liquidity_usd * 0.1,  # 10% of liquidity as daily volume
                "pool_type": "stableswap"
            }
            
        except Exception as e:
            logger.error(f"Error getting Curve liquidity info: {e}")
            return {"liquidity_usd": 0, "volume_24h": 0}
    
    async def _estimate_swap_gas_cost(self) -> Decimal:
        """Estimate gas cost for a Curve swap"""
        try:
            gas_price = await self.engine.w3.eth.gas_price
            gas_limit = 180000  # Curve swaps can be gas intensive
            
            # Get MATIC price in USD
            matic_price_usd = Decimal("0.8")
            
            gas_cost_matic = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_matic * matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating Curve gas cost: {e}")
            return Decimal("0.7")  # Default $0.7 estimate
