import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import FlashLoanParams, ExecutionResult

from .engine import EthereumEngine
from .config import EthereumConfig

logger = logging.getLogger(__name__)

class FlashLoanEngine:
    """Flash loan engine for Ethereum (Aave, dYdX, Balancer)"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        self.providers = {
            "aave": {
                "address": config.AAVE_LENDING_POOL,
                "fee_percentage": Decimal("0.0009")  # 0.09%
            },
            "dydx": {
                "address": config.DYDX_SOLO_MARGIN,
                "fee_percentage": Decimal("0.0002")  # 0.02%
            }
        }
        
    async def initialize(self):
        """Initialize the flash loan engine"""
        logger.info("Initializing flash loan engine...")
        
        # Load contract ABIs
        self.aave_lending_pool_abi = await self.engine.load_abi("AaveLendingPool")
        self.balancer_vault_abi = await self.engine.load_abi("BalancerVault")
        self.dydx_solo_margin_abi = await self.engine.load_abi("DydxSoloMargin")
        
        # Initialize contract interfaces
        self.aave_lending_pool = self.engine.w3.eth.contract(
            address=self.engine.w3.to_checksum_address(self.providers["aave"]["address"]),
            abi=self.aave_lending_pool_abi
        )
        
        self.balancer_vault = self.engine.w3.eth.contract(
            address=self.engine.w3.to_checksum_address(self.providers["balancer"]["address"]),
            abi=self.balancer_vault_abi
        )
        
        # Initialize dYdX interface if available
        if self.providers["dydx"]["address"]:
            self.dydx_solo_margin = self.engine.w3.eth.contract(
                address=self.engine.w3.to_checksum_address(self.providers["dydx"]["address"]),
                abi=self.dydx_solo_margin_abi
            )

    async def get_available_liquidity(self, token_address):
        """Get available liquidity for a token across all providers"""
        liquidity = {}
        
        # Get token details
        token_contract = self.engine.get_token_contract(token_address)
        token_symbol = await self.engine.call_contract_function(token_contract, "symbol")
        token_decimals = await self.engine.call_contract_function(token_contract, "decimals")
        
        # Check Aave liquidity
        try:
            aave_liquidity = await self.engine.call_contract_function(
                self.aave_lending_pool,
                "getReserveData",
                token_address
            )
            liquidity["aave"] = self.engine.w3.from_wei(aave_liquidity[0], 'ether')
        except Exception as e:
            logger.error(f"Error getting Aave liquidity for {token_symbol}: {e}")
            liquidity["aave"] = 0
        
        # Check Balancer liquidity
        try:
            balancer_pool_id = self.config.BALANCER_POOLS.get(token_symbol)
            if balancer_pool_id:
                balancer_liquidity = await self.engine.call_contract_function(
                    self.balancer_vault,
                    "getPoolTokenInfo",
                    balancer_pool_id,
                    token_address
                )
                liquidity["balancer"] = self.engine.w3.from_wei(balancer_liquidity[0], 'ether')
            else:
                liquidity["balancer"] = 0
        except Exception as e:
            logger.error(f"Error getting Balancer liquidity for {token_symbol}: {e}")
            liquidity["balancer"] = 0
        
        return liquidity
    
    async def prepare_flash_loan(self, strategy_type, params):
        """Prepare flash loan parameters based on strategy type"""
        if strategy_type == "cross":
            return await self._prepare_cross_flash_loan(params)
        elif strategy_type == "triangular":
            return await self._prepare_triangular_flash_loan(params)
        elif strategy_type == "mempool":
            return await self._prepare_mempool_flash_loan(params)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
    
    async def _prepare_cross_flash_loan(self, params):
        """Prepare flash loan for cross-exchange arbitrage"""
        token_address = params["tokenA"]
        amount = params["amountIn"]
        
        # Get best provider based on liquidity and fees
        provider = await self._get_best_provider(token_address, amount)
        
        # Prepare flash loan data
        flash_data = {
            "provider": provider,
            "tokens": [token_address],
            "amounts": [amount],
            "modes": [0],  # 0 = no debt, just flash loan
            "params": self.engine.w3.encode_abi(
                ["address", "address", "uint256", "address", "address", "uint256", "uint256", "uint256"],
                [
                    params["tokenA"],
                    params["tokenB"],
                    params["amountIn"],
                    params["buyRouter"],
                    params["sellRouter"],
                    params["buyFee"],
                    params["sellFee"],
                    params["minProfit"]
                ]
            )
        }
        
        return flash_data
    
    async def _prepare_triangular_flash_loan(self, params):
        """Prepare flash loan for triangular arbitrage"""
        token_address = params["path"][0]
        amount = params["amountIn"]
        
        # Get best provider based on liquidity and fees
        provider = await self._get_best_provider(token_address, amount)
        
        # Prepare flash loan data
        flash_data = {
            "provider": provider,
            "tokens": [token_address],
            "amounts": [amount],
            "modes": [0],  # 0 = no debt, just flash loan
            "params": self.engine.w3.encode_abi(
                ["address[]", "address[]", "uint256[]", "uint256", "uint256"],
                [
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"]
                ]
            )
        }
        
        return flash_data
    
    async def _prepare_mempool_flash_loan(self, params):
        """Prepare flash loan for mempool backrun arbitrage"""
        token_address = params["path"][0]
        amount = params["amountIn"]
        
        # Get best provider based on liquidity and fees
        provider = await self._get_best_provider(token_address, amount)
        
        # Prepare flash loan data
        flash_data = {
            "provider": provider,
            "tokens": [token_address],
            "amounts": [amount],
            "modes": [0],  # 0 = no debt, just flash loan
            "params": self.engine.w3.encode_abi(
                ["bytes32", "address[]", "address[]", "uint256[]", "uint256", "uint256", "uint256"],
                [
                    params["targetTxHash"],
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"],
                    params["maxGasPrice"]
                ]
            )
        }
        
        return flash_data
    
    async def _get_best_provider(self, token_address, amount):
        """Get the best flash loan provider based on liquidity and fees"""
        liquidity = await self.get_available_liquidity(token_address)
        
        # Check if any provider has enough liquidity
        valid_providers = {}
        for provider, available in liquidity.items():
            if available >= amount:
                valid_providers[provider] = self.providers[provider]["fee"]
        
        if not valid_providers:
            raise ValueError(f"No provider has enough liquidity for token {token_address}")
        
        # Return provider with lowest fee
        best_provider = min(valid_providers.items(), key=lambda x: x[1])[0]
        return best_provider
    
    async def estimate_flash_loan_cost(self, token_address, amount, provider=None):
        """Estimate the cost of a flash loan"""
        if not provider:
            provider = await self._get_best_provider(token_address, amount)
            
        fee_percentage = self.providers[provider]["fee"]
        fee_amount = amount * fee_percentage / 100
        
        return {
            "provider": provider,
            "fee_percentage": fee_percentage,
            "fee_amount": fee_amount,
            "total_repayment": amount + fee_amount
        }
    
    async def get_best_provider(self, token: str, amount: Decimal) -> str:
        """Get the best flash loan provider for given token and amount"""
        try:
            best_provider = "aave"
            lowest_fee = Decimal("999999")
            
            for provider_name in self.providers:
                # Check liquidity
                liquidity = await self.get_available_liquidity(token, provider_name)
                if liquidity < amount:
                    continue
                
                # Calculate fee
                fee = await self.calculate_flash_loan_fee(amount, token, provider_name)
                
                if fee < lowest_fee:
                    lowest_fee = fee
                    best_provider = provider_name
            
            logger.info(f"Best flash loan provider for {amount} {token}: {best_provider} (fee: {lowest_fee})")
            return best_provider
            
        except Exception as e:
            logger.error(f"Error finding best provider: {e}")
            return "aave"  # Default to Aave
    
    async def estimate_gas_cost(self, params: FlashLoanParams) -> int:
        """Estimate gas cost for flash loan execution"""
        try:
            # Base gas cost varies by provider and callback complexity
            base_costs = {
                "aave": 300000,
                "dydx": 250000
            }
            
            base_cost = base_costs.get(params.provider, 300000)
            
            # Add callback complexity cost
            callback_complexity = len(params.callback_data.get("operations", []))
            callback_cost = callback_complexity * 50000
            
            total_gas = base_cost + callback_cost
            
            return min(total_gas, 800000)  # Cap at 800k gas
            
        except Exception as e:
            logger.error(f"Error estimating gas cost: {e}")
            return 500000  # Default estimate