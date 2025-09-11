import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional
from .engine import EthereumEngine
from .erc20_helper import ERC20Helper
from .abi_encoder import SwapCallDataEncoder

logger = logging.getLogger(__name__)

class SwapOrchestrator:
    """Orchestrates the complete swap flow including approvals"""
    
    def __init__(self, engine: EthereumEngine):
        self.engine = engine
        
    async def execute_swap_with_approval(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        router_address: str,
        swap_calldata: str,
        min_allowance: Decimal = None
    ) -> Dict[str, Any]:
        """Execute a complete swap including approval if needed"""
        try:
            if not self.engine.erc20_helper:
                raise ValueError("ERC20Helper not available")
            
            # Get token info for proper unit handling
            token_info = await self.engine.erc20_helper.get_token_info(token_in)
            if not token_info:
                raise ValueError(f"Could not get token info for {token_in}")
            
            # Check current allowance (returns in decimal units)
            current_allowance = await self.engine.erc20_helper.get_allowance(
                token_in, 
                router_address
            )
            
            # Determine if approval is needed (both in decimal units)
            required_amount = min_allowance or amount_in
            needs_approval = current_allowance < required_amount
            
            transactions = []
            
            if needs_approval:
                # Build approval transaction (helper handles decimal to wei conversion)
                approve_amount = required_amount * 2  # Approve 2x for gas efficiency
                approve_tx = await self.engine.erc20_helper.build_approve_transaction(
                    token_in,
                    router_address,
                    approve_amount
                )
                
                if approve_tx:
                    transactions.append({
                        "type": "approve",
                        "tx_data": approve_tx
                    })
                    logger.info(f"Approval needed for {token_in} -> {router_address}")
            
            # Add swap transaction
            transactions.append({
                "type": "swap", 
                "tx_data": {
                    "to": router_address,
                    "value": 0,
                    "data": swap_calldata
                }
            })
            
            # Execute transactions sequentially
            tx_hashes = []
            for tx in transactions:
                try:
                    tx_hash = await self.engine.execute_transaction(tx["tx_data"])
                    tx_hashes.append({
                        "type": tx["type"],
                        "hash": tx_hash
                    })
                    
                    # Wait for approval before swap
                    if tx["type"] == "approve":
                        await self._wait_for_confirmation(tx_hash)
                        
                except Exception as e:
                    logger.error(f"Transaction failed ({tx['type']}): {e}")
                    return {
                        "success": False,
                        "error": str(e),
                        "completed_transactions": tx_hashes
                    }
            
            return {
                "success": True,
                "transactions": tx_hashes,
                "needs_approval": needs_approval
            }
            
        except Exception as e:
            logger.error(f"Swap orchestration failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _wait_for_confirmation(self, tx_hash: str, max_wait: int = 60) -> bool:
        """Wait for transaction confirmation"""
        try:
            for _ in range(max_wait):
                try:
                    receipt = await self.engine.w3.eth.get_transaction_receipt(tx_hash)
                    if receipt and receipt.blockNumber:
                        return receipt.status == 1
                except Exception:
                    # Transaction not yet mined
                    pass
                await asyncio.sleep(1)
            
            logger.warning(f"Transaction {tx_hash} not confirmed within {max_wait}s")
            return False
            
        except Exception as e:
            logger.error(f"Error waiting for confirmation: {e}")
            return False
    
    async def build_multicall_transaction(
        self,
        router_address: str,
        calls: List[str]
    ) -> Dict[str, Any]:
        """Build a multicall transaction combining multiple operations"""
        try:
            multicall_data = SwapCallDataEncoder.encode_multicall(calls)
            
            return {
                "to": router_address,
                "value": 0,
                "data": multicall_data,
                "gas": len(calls) * 100000  # Estimate based on call count
            }
            
        except Exception as e:
            logger.error(f"Error building multicall: {e}")
            return {}
    
    async def estimate_swap_gas(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        router_address: str,
        swap_calldata: str
    ) -> int:
        """Estimate total gas including potential approval"""
        try:
            base_gas = 21000  # Base transaction cost
            swap_gas = 150000  # Estimated swap gas
            
            # Check if approval is needed
            if self.engine.erc20_helper:
                allowance = await self.engine.erc20_helper.get_allowance(
                    token_in, 
                    router_address
                )
                
                if allowance < amount_in:
                    base_gas += 60000  # Add approval gas
            
            return base_gas + swap_gas
            
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return 250000  # Conservative fallback