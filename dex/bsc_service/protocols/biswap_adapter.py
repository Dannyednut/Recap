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

class BiswapAdapter(BaseProtocolAdapter):
    """Biswap protocol adapter for BSC"""
    
    def __init__(self, engine, config):
        super().__init__(engine, config)
        self.protocol_name = "Biswap"
        self.router_address = "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8"
        self.factory_address = "0x858E3312ed3A876947EA49d572A7C42DE08af7EE"
        self.fee_rate = Decimal("0.001")  # 0.1%
        
        # Contract ABIs (similar to PancakeSwap)
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
            logger.error(f"Error getting Biswap pair address: {e}")
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
            logger.error(f"Error getting Biswap reserves: {e}")
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
            logger.error(f"Error getting Biswap quote: {e}")
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
            logger.error(f"Error executing Biswap swap: {e}")
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
            
            # Get token prices in USD (simplified)
            token0_price_usd = await self._get_token_price_usd(token0)
            token1_price_usd = await self._get_token_price_usd(token1)
            
            # Calculate liquidity in USD
            liquidity_usd = float(reserve0 * token0_price_usd + reserve1 * token1_price_usd)
            
            return {
                "pair_address": pair_address,
                "reserve0": float(reserve0),
                "reserve1": float(reserve1),
                "liquidity_usd": liquidity_usd,
                "volume_24h": 0  # Would need API integration
            }
            
        except Exception as e:
            logger.error(f"Error getting Biswap liquidity info: {e}")
            return {"liquidity_usd": 0, "volume_24h": 0}
    
    async def _estimate_swap_gas_cost(self) -> Decimal:
        """Estimate gas cost for a swap"""
        try:
            gas_price = await self.engine.w3.eth.gas_price
            gas_limit = 150000  # Typical gas limit for Biswap swap
            
            # Get BNB price in USD
            bnb_price_usd = await self._get_token_price_usd("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
            
            gas_cost_bnb = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_bnb * bnb_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating Biswap gas cost: {e}")
            return Decimal("4")  # Default $4 estimate
    
    async def _get_token_price_usd(self, token_address: str) -> Decimal:
        """Get token price in USD (simplified implementation)"""
        try:
            # Common token prices (hardcoded for demo)
            token_prices = {
                "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c": Decimal("300"),  # WBNB
                "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56": Decimal("1"),    # BUSD
                "0x55d398326f99059fF775485246999027B3197955": Decimal("1"),    # USDT
                "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d": Decimal("1"),    # USDC
            }
            
            return token_prices.get(token_address, Decimal("1"))
            
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return Decimal("1")


class ApeSwapAdapter(BaseProtocolAdapter):
    """ApeSwap protocol adapter for BSC"""
    
    def __init__(self, engine, config):
        super().__init__(engine, config)
        self.protocol_name = "ApeSwap"
        self.router_address = "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7"
        self.factory_address = "0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6"
        self.fee_rate = Decimal("0.002")  # 0.2%
        
        # Contract ABIs (similar to other DEXs)
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
            logger.error(f"Error getting ApeSwap pair address: {e}")
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
            logger.error(f"Error getting ApeSwap reserves: {e}")
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
            logger.error(f"Error getting ApeSwap quote: {e}")
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
            logger.error(f"Error executing ApeSwap swap: {e}")
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
            
            # Get token prices in USD (simplified)
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
            logger.error(f"Error getting ApeSwap liquidity info: {e}")
            return {"liquidity_usd": 0, "volume_24h": 0}
    
    async def _estimate_swap_gas_cost(self) -> Decimal:
        """Estimate gas cost for a swap"""
        try:
            gas_price = await self.engine.w3.eth.gas_price
            gas_limit = 160000  # Typical gas limit for ApeSwap
            
            # Get BNB price in USD
            bnb_price_usd = await self._get_token_price_usd("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
            
            gas_cost_bnb = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_bnb * bnb_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating ApeSwap gas cost: {e}")
            return Decimal("5")  # Default $5 estimate
    
    async def _get_token_price_usd(self, token_address: str) -> Decimal:
        """Get token price in USD (simplified implementation)"""
        try:
            # Common token prices (hardcoded for demo)
            token_prices = {
                "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c": Decimal("300"),  # WBNB
                "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56": Decimal("1"),    # BUSD
                "0x55d398326f99059fF775485246999027B3197955": Decimal("1"),    # USDT
                "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d": Decimal("1"),    # USDC
            }
            
            return token_prices.get(token_address, Decimal("1"))
            
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return Decimal("1")
