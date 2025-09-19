import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from web3 import AsyncWeb3
from web3.contract import AsyncContract

from .base_adapter import BaseProtocolAdapter
from ..config import PolygonConfig
from ...shared.contract_addresses import get_router_address, get_factory_address, get_base_tokens
from ...shared.abi_fetcher import ABIFetcher, FALLBACK_ABIS

logger = logging.getLogger(__name__)

class QuickSwapAdapter(BaseProtocolAdapter):
    """QuickSwap protocol adapter for Polygon"""
    
    def __init__(self, engine, config):
        super().__init__(engine, config)
        self.protocol_name = "QuickSwap"
        # Use network-aware addresses
        self.router_address = get_router_address('polygon', 'quickswap')
        self.factory_address = get_factory_address('polygon', 'quickswap')
        self.fee_rate = Decimal("0.003")  # 0.3%
        
        # ABI fetcher for dynamic contract interaction
        self.abi_fetcher = ABIFetcher()
        self.base_tokens = get_base_tokens('polygon')
        
        # Contract ABIs
        self.factory_abi = [
            {"constant": True, "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}], 
             "name": "getPair", "outputs": [{"name": "pair", "type": "address"}], "type": "function"}
        ]
        
        self.pair_abi = [
            {"constant": True, "inputs": [], "name": "getReserves", 
             "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, 
                        {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"}
        ]
        
        self.router_abi = [
            {"inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}], 
             "name": "getAmountsOut", "outputs": [{"name": "amounts", "type": "uint256[]"}], "type": "function"},
            {"inputs": [{"name": "amountOut", "type": "uint256"}, {"name": "path", "type": "address[]"}], 
             "name": "getAmountsIn", "outputs": [{"name": "amounts", "type": "uint256[]"}], "type": "function"},
            {"inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "amountOutMin", "type": "uint256"}, 
                       {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}], 
             "name": "swapExactTokensForTokens", "outputs": [{"name": "amounts", "type": "uint256[]"}], "type": "function"}
        ]
    
    async def get_pair_address(self, token0: str, token1: str) -> Optional[str]:
        """Get pair address for two tokens"""
        try:
            factory_contract = self.engine.w3.eth.contract(
                address=self.factory_address, 
                abi=self.factory_abi
            )
            
            pair_address = await factory_contract.functions.getPair(token0, token1).call()
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None
            
            return pair_address
            
        except Exception as e:
            logger.error(f"Error getting QuickSwap pair address: {e}")
            return None
    
    async def get_reserves(self, pair_address: str) -> Tuple[Decimal, Decimal]:
        """Get reserves for a trading pair"""
        try:
            pair_contract = self.engine.w3.eth.contract(
                address=pair_address, 
                abi=self.pair_abi
            )
            
            reserves = await pair_contract.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])
            
            return reserve0, reserve1
            
        except Exception as e:
            logger.error(f"Error getting QuickSwap reserves: {e}")
            return Decimal("0"), Decimal("0")
    
    async def get_quote(self, amount_in: Decimal, token_in: str, token_out: str) -> SwapQuote:
        """Get quote for a swap"""
        try:
            router_contract = self.engine.w3.eth.contract(
                address=self.router_address, 
                abi=self.router_abi
            )
            
            path = [token_in, token_out]
            amounts = await router_contract.functions.getAmountsOut(int(amount_in), path).call()
            
            amount_out = Decimal(amounts[1])
            
            # Calculate price impact
            price_impact = await self.get_price_impact(amount_in, token_in, token_out)
            
            # Calculate gas cost (estimated)
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
            logger.error(f"Error getting QuickSwap quote: {e}")
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
        """Execute a swap transaction"""
        try:
            router_contract = self.engine.w3.eth.contract(
                address=self.router_address, 
                abi=self.router_abi
            )
            
            path = [token_in, token_out]
            deadline = int(asyncio.get_event_loop().time()) + 1200  # 20 minutes
            
            # Build transaction
            transaction = router_contract.functions.swapExactTokensForTokens(
                int(amount_in),
                int(min_amount_out),
                path,
                to_address,
                deadline
            ).build_transaction({
                'from': self.engine.wallet_address,
                'gas': 200000,
                'gasPrice': await self.engine.w3.eth.gas_price,
                'nonce': await self.engine.w3.eth.get_transaction_count(self.engine.wallet_address)
            })
            
            # Sign and send transaction
            signed_txn = self.engine.w3.eth.account.sign_transaction(transaction, self.engine.private_key)
            tx_hash = await self.engine.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            return {
                "success": True,
                "tx_hash": tx_hash.hex(),
                "protocol": self.protocol_name,
                "amount_in": float(amount_in),
                "min_amount_out": float(min_amount_out)
            }
            
        except Exception as e:
            logger.error(f"Error executing QuickSwap swap: {e}")
            return {
                "success": False,
                "error": str(e),
                "protocol": self.protocol_name
            }
    
    async def get_liquidity_info(self, token0: str, token1: str) -> Dict[str, Any]:
        """Get liquidity information for a token pair"""
        try:
            pair_address = await self.get_pair_address(token0, token1)
            if not pair_address:
                return {"liquidity_usd": 0, "volume_24h": 0}
            
            reserve0, reserve1 = await self.get_reserves(pair_address)
            
            # Get token prices in USD (simplified - would need price oracle)
            token0_price_usd = await self._get_token_price_usd(token0)
            token1_price_usd = await self._get_token_price_usd(token1)
            
            # Calculate liquidity in USD
            liquidity_usd = float(reserve0 * token0_price_usd + reserve1 * token1_price_usd)
            
            return {
                "pair_address": pair_address,
                "reserve0": float(reserve0),
                "reserve1": float(reserve1),
                "liquidity_usd": liquidity_usd,
                "volume_24h": 0  # Would need to query from API or events
            }
            
        except Exception as e:
            logger.error(f"Error getting QuickSwap liquidity info: {e}")
            return {"liquidity_usd": 0, "volume_24h": 0}
    
    async def _estimate_swap_gas_cost(self) -> Decimal:
        """Estimate gas cost for a swap"""
        try:
            gas_price = await self.engine.w3.eth.gas_price
            gas_limit = 150000  # Typical gas limit for QuickSwap swap
            
            # Get MATIC price in USD (simplified)
            matic_price_usd = await self._get_token_price_usd("0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270")
            
            gas_cost_matic = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_matic * matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating gas cost: {e}")
            return Decimal("0.5")  # Default $0.5 estimate
    
    async def _get_token_price_usd(self, token_address: str) -> Decimal:
        """Get token price in USD (simplified implementation)"""
        try:
            # Common Polygon token prices (hardcoded for demo)
            token_prices = {
                "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270": Decimal("0.8"),   # WMATIC
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": Decimal("1.0"),   # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": Decimal("1.0"),   # USDT
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063": Decimal("1.0"),   # DAI
                "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619": Decimal("2500"), # WETH
                "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6": Decimal("45000") # WBTC
            }
            
            return token_prices.get(token_address, Decimal("1"))
            
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return Decimal("1")


class SushiSwapPolygonAdapter(BaseProtocolAdapter):
    """SushiSwap protocol adapter for Polygon"""
    
    def __init__(self, engine, config):
        super().__init__(engine, config)
        self.protocol_name = "SushiSwap"
        self.router_address = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
        self.factory_address = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"
        self.fee_rate = Decimal("0.003")  # 0.3%
        
        # Contract ABIs (similar to QuickSwap)
        self.factory_abi = [
            {"constant": True, "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}], 
             "name": "getPair", "outputs": [{"name": "pair", "type": "address"}], "type": "function"}
        ]
        
        self.pair_abi = [
            {"constant": True, "inputs": [], "name": "getReserves", 
             "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, 
                        {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"}
        ]
        
        self.router_abi = [
            {"inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}], 
             "name": "getAmountsOut", "outputs": [{"name": "amounts", "type": "uint256[]"}], "type": "function"},
            {"inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "amountOutMin", "type": "uint256"}, 
                       {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}], 
             "name": "swapExactTokensForTokens", "outputs": [{"name": "amounts", "type": "uint256[]"}], "type": "function"}
        ]
    
    async def get_pair_address(self, token0: str, token1: str) -> Optional[str]:
        """Get pair address for two tokens"""
        try:
            factory_contract = self.engine.w3.eth.contract(
                address=self.factory_address, 
                abi=self.factory_abi
            )
            
            pair_address = await factory_contract.functions.getPair(token0, token1).call()
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None
            
            return pair_address
            
        except Exception as e:
            logger.error(f"Error getting SushiSwap pair address: {e}")
            return None
    
    async def get_reserves(self, pair_address: str) -> Tuple[Decimal, Decimal]:
        """Get reserves for a trading pair"""
        try:
            pair_contract = self.engine.w3.eth.contract(
                address=pair_address, 
                abi=self.pair_abi
            )
            
            reserves = await pair_contract.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])
            
            return reserve0, reserve1
            
        except Exception as e:
            logger.error(f"Error getting SushiSwap reserves: {e}")
            return Decimal("0"), Decimal("0")
    
    async def get_quote(self, amount_in: Decimal, token_in: str, token_out: str) -> SwapQuote:
        """Get quote for a swap"""
        try:
            router_contract = self.engine.w3.eth.contract(
                address=self.router_address, 
                abi=self.router_abi
            )
            
            path = [token_in, token_out]
            amounts = await router_contract.functions.getAmountsOut(int(amount_in), path).call()
            
            amount_out = Decimal(amounts[1])
            
            # Calculate price impact
            price_impact = await self.get_price_impact(amount_in, token_in, token_out)
            
            # Calculate gas cost
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
            logger.error(f"Error getting SushiSwap quote: {e}")
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
        """Execute a swap transaction"""
        try:
            router_contract = self.engine.w3.eth.contract(
                address=self.router_address, 
                abi=self.router_abi
            )
            
            path = [token_in, token_out]
            deadline = int(asyncio.get_event_loop().time()) + 1200  # 20 minutes
            
            # Build transaction
            transaction = router_contract.functions.swapExactTokensForTokens(
                int(amount_in),
                int(min_amount_out),
                path,
                to_address,
                deadline
            ).build_transaction({
                'from': self.engine.wallet_address,
                'gas': 200000,
                'gasPrice': await self.engine.w3.eth.gas_price,
                'nonce': await self.engine.w3.eth.get_transaction_count(self.engine.wallet_address)
            })
            
            # Sign and send transaction
            signed_txn = self.engine.w3.eth.account.sign_transaction(transaction, self.engine.private_key)
            tx_hash = await self.engine.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            return {
                "success": True,
                "tx_hash": tx_hash.hex(),
                "protocol": self.protocol_name,
                "amount_in": float(amount_in),
                "min_amount_out": float(min_amount_out)
            }
            
        except Exception as e:
            logger.error(f"Error executing SushiSwap swap: {e}")
            return {
                "success": False,
                "error": str(e),
                "protocol": self.protocol_name
            }
    
    async def get_liquidity_info(self, token0: str, token1: str) -> Dict[str, Any]:
        """Get liquidity information for a token pair"""
        try:
            pair_address = await self.get_pair_address(token0, token1)
            if not pair_address:
                return {"liquidity_usd": 0, "volume_24h": 0}
            
            reserve0, reserve1 = await self.get_reserves(pair_address)
            
            # Get token prices in USD
            token0_price_usd = await self._get_token_price_usd(token0)
            token1_price_usd = await self._get_token_price_usd(token1)
            
            # Calculate liquidity in USD
            liquidity_usd = float(reserve0 * token0_price_usd + reserve1 * token1_price_usd)
            
            return {
                "pair_address": pair_address,
                "reserve0": float(reserve0),
                "reserve1": float(reserve1),
                "liquidity_usd": liquidity_usd,
                "volume_24h": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting SushiSwap liquidity info: {e}")
            return {"liquidity_usd": 0, "volume_24h": 0}
    
    async def _estimate_swap_gas_cost(self) -> Decimal:
        """Estimate gas cost for a swap"""
        try:
            gas_price = await self.engine.w3.eth.gas_price
            gas_limit = 160000  # Typical gas limit for SushiSwap
            
            # Get MATIC price in USD
            matic_price_usd = await self._get_token_price_usd("0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270")
            
            gas_cost_matic = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_matic * matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating SushiSwap gas cost: {e}")
            return Decimal("0.6")  # Default $0.6 estimate
    
    async def _get_token_price_usd(self, token_address: str) -> Decimal:
        """Get token price in USD (simplified implementation)"""
        try:
            # Common Polygon token prices (hardcoded for demo)
            token_prices = {
                "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270": Decimal("0.8"),   # WMATIC
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": Decimal("1.0"),   # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": Decimal("1.0"),   # USDT
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063": Decimal("1.0"),   # DAI
                "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619": Decimal("2500"), # WETH
                "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6": Decimal("45000") # WBTC
            }
            
            return token_prices.get(token_address, Decimal("1"))
            
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return Decimal("1")
