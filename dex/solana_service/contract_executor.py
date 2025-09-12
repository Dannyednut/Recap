"""
Solana contract execution interface for arbitrage
Uses Solana programs and Jupiter aggregator for DEX interactions
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.system_program import transfer, TransferParams
from solana.rpc.commitment import Confirmed
import json
import os
from ..shared.mev_protection import UniversalMEVProtection
from .engine import SolanaEngine
from .config import SolanaConfig

logger = logging.getLogger(__name__)

class SolanaContractExecutor:
    """Execute arbitrage opportunities on Solana using Jupiter and native programs"""
    
    # Major Solana DEX program IDs
    JUPITER_PROGRAM_ID = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    RAYDIUM_AMM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    ORCA_PROGRAM_ID = "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP"
    SERUM_PROGRAM_ID = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
    
    # Jupiter API endpoints
    JUPITER_API_BASE = "https://quote-api.jup.ag/v6"
    
    def __init__(self, engine: SolanaEngine, config: SolanaConfig):
        """Initialize Solana contract executor"""
        self.engine = engine
        self.config = config
        self.client = engine.client
        self.keypair = engine.keypair
        self.wallet_address = str(engine.keypair.public_key)
        
        # MEV Protection for Solana (using 101 as chain_id identifier)
        self.mev_protection = UniversalMEVProtection(
            chain_id=101,
            w3=None,  # Solana doesn't use web3
            private_key=config.PRIVATE_KEY
        )
        
        # Program addresses
        self.programs = {
            "jupiter": PublicKey(self.JUPITER_PROGRAM_ID),
            "raydium": PublicKey(self.RAYDIUM_AMM_PROGRAM_ID),
            "orca": PublicKey(self.ORCA_PROGRAM_ID),
            "serum": PublicKey(self.SERUM_PROGRAM_ID)
        }
        
    async def initialize(self):
        """Initialize the Solana contract executor"""
        logger.info("Initializing Solana contract executor...")
        
        # Verify connection to Solana network
        try:
            health = await self.client.get_health()
            logger.info(f"Solana RPC health: {health}")
        except Exception as e:
            logger.error(f"Failed to connect to Solana RPC: {e}")
            raise
        
        # Get wallet balance
        try:
            balance = await self.client.get_balance(self.keypair.public_key)
            logger.info(f"Wallet balance: {balance.value / 1e9:.4f} SOL")
        except Exception as e:
            logger.error(f"Failed to get wallet balance: {e}")
            
        logger.info("Solana contract executor initialized")
    
    async def execute_jupiter_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50  # 0.5% slippage
    ) -> Optional[str]:
        """Execute swap using Jupiter aggregator"""
        try:
            # Get quote from Jupiter
            quote = await self._get_jupiter_quote(
                input_mint, output_mint, amount, slippage_bps
            )
            
            if not quote:
                logger.error("Failed to get Jupiter quote")
                return None
            
            # Get swap transaction from Jupiter
            swap_tx = await self._get_jupiter_swap_transaction(quote)
            
            if not swap_tx:
                logger.error("Failed to get Jupiter swap transaction")
                return None
            
            # Sign and send transaction
            signed_tx = self.keypair.sign(swap_tx)
            
            # Submit via MEV protection if enabled
            if self.config.USE_MEV_PROTECTION:
                tx_data = {
                    "raw_tx": signed_tx.serialize().hex(),
                    "priority_fee": 5000,  # Solana uses micro-lamports
                    "max_fee": 10000
                }
                
                bundle_hash = await self.mev_protection.submit_arbitrage_bundle(
                    [tx_data], 0  # Solana doesn't have block numbers like Ethereum
                )
                
                if bundle_hash:
                    logger.info(f"Solana Jupiter swap submitted via MEV protection: {bundle_hash}")
                    return bundle_hash
                else:
                    logger.warning("Solana MEV protection failed, falling back to direct submission")
            
            # Fallback to direct submission
            result = await self.client.send_transaction(
                signed_tx,
                opts={"skip_preflight": True, "max_retries": 3}
            )
            
            logger.info(f"Jupiter swap transaction sent: {result.value}")
            return result.value
            
        except Exception as e:
            logger.error(f"Error executing Jupiter swap: {e}")
            return None
    
    async def execute_arbitrage(self, params: Dict[str, Any]) -> Optional[str]:
        """Execute cross-DEX arbitrage on Solana"""
        try:
            logger.info(f"Executing Solana arbitrage: {params}")
            
            # Step 1: Swap on first DEX
            first_swap_result = await self.execute_jupiter_swap(
                params["input_mint"],
                params["intermediate_mint"],
                params["amount_in"]
            )
            
            if not first_swap_result:
                logger.error("First swap failed")
                return None
            
            # Wait for confirmation
            await self._wait_for_confirmation(first_swap_result)
            
            # Get intermediate token balance
            intermediate_balance = await self._get_token_balance(
                params["intermediate_mint"]
            )
            
            # Step 2: Swap on second DEX
            second_swap_result = await self.execute_jupiter_swap(
                params["intermediate_mint"],
                params["output_mint"],
                intermediate_balance
            )
            
            if not second_swap_result:
                logger.error("Second swap failed")
                return None
            
            logger.info(f"Solana arbitrage completed: {second_swap_result}")
            return second_swap_result
            
        except Exception as e:
            logger.error(f"Error executing Solana arbitrage: {e}")
            return None
    
    async def execute_backrun_arbitrage(self, params: Dict[str, Any]) -> Optional[str]:
        """Execute backrun arbitrage on Solana"""
        try:
            logger.info(f"Executing Solana backrun arbitrage: {params}")
            
            # Monitor target transaction
            target_tx = params.get("target_tx_signature")
            if target_tx:
                # Wait for target transaction confirmation
                await self._wait_for_confirmation(target_tx)
            
            # Execute arbitrage sequence
            return await self.execute_arbitrage(params)
            
        except Exception as e:
            logger.error(f"Error executing Solana backrun arbitrage: {e}")
            return None
    
    async def _get_jupiter_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int
    ) -> Optional[Dict[str, Any]]:
        """Get quote from Jupiter API"""
        try:
            import aiohttp
            
            url = f"{self.JUPITER_API_BASE}/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": slippage_bps
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Jupiter quote API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting Jupiter quote: {e}")
            return None
    
    async def _get_jupiter_swap_transaction(self, quote: Dict[str, Any]) -> Optional[Transaction]:
        """Get swap transaction from Jupiter API"""
        try:
            import aiohttp
            
            url = f"{self.JUPITER_API_BASE}/swap"
            payload = {
                "quoteResponse": quote,
                "userPublicKey": str(self.keypair.public_key),
                "wrapAndUnwrapSol": True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        # Deserialize transaction
                        tx_data = result.get("swapTransaction")
                        if tx_data:
                            return Transaction.deserialize(bytes.fromhex(tx_data))
                    else:
                        logger.error(f"Jupiter swap API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting Jupiter swap transaction: {e}")
            return None
    
    async def _wait_for_confirmation(self, signature: str, timeout: int = 60) -> bool:
        """Wait for transaction confirmation"""
        try:
            import time
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    result = await self.client.get_signature_status(signature)
                    if result.value and result.value.confirmation_status == Confirmed:
                        return True
                except Exception:
                    pass
                
                await asyncio.sleep(1)
            
            logger.warning(f"Transaction confirmation timeout: {signature}")
            return False
            
        except Exception as e:
            logger.error(f"Error waiting for confirmation: {e}")
            return False
    
    async def _get_token_balance(self, mint_address: str) -> int:
        """Get token balance for the wallet"""
        try:
            # Get token accounts for the wallet
            response = await self.client.get_token_accounts_by_owner(
                self.keypair.public_key,
                {"mint": PublicKey(mint_address)}
            )
            
            if response.value:
                # Get balance of the first token account
                account_info = response.value[0]
                balance_response = await self.client.get_token_account_balance(
                    account_info.pubkey
                )
                return int(balance_response.value.amount)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting token balance: {e}")
            return 0
    
    async def get_arbitrage_quote(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get quote for potential arbitrage opportunity"""
        try:
            # Get quotes for both legs of the arbitrage
            first_quote = await self._get_jupiter_quote(
                params["input_mint"],
                params["intermediate_mint"],
                params["amount_in"],
                50  # 0.5% slippage
            )
            
            if not first_quote:
                return {"error": "Failed to get first quote"}
            
            intermediate_amount = int(first_quote["outAmount"])
            
            second_quote = await self._get_jupiter_quote(
                params["intermediate_mint"],
                params["output_mint"],
                intermediate_amount,
                50
            )
            
            if not second_quote:
                return {"error": "Failed to get second quote"}
            
            final_amount = int(second_quote["outAmount"])
            profit = final_amount - params["amount_in"]
            
            return {
                "input_amount": params["amount_in"],
                "intermediate_amount": intermediate_amount,
                "output_amount": final_amount,
                "profit": profit,
                "profit_percentage": (profit / params["amount_in"]) * 100,
                "first_quote": first_quote,
                "second_quote": second_quote
            }
            
        except Exception as e:
            logger.error(f"Error getting Solana arbitrage quote: {e}")
            return {"error": str(e)}
    
    async def emergency_withdraw(self, token_mint: str, amount: int) -> Optional[str]:
        """Emergency withdraw tokens from wallet"""
        try:
            if token_mint == "So11111111111111111111111111111111111111112":  # SOL
                # Transfer SOL
                transfer_ix = transfer(
                    TransferParams(
                        from_pubkey=self.keypair.public_key,
                        to_pubkey=self.keypair.public_key,  # Send to self for now
                        lamports=amount
                    )
                )
                
                transaction = Transaction().add(transfer_ix)
                result = await self.client.send_transaction(transaction, self.keypair)
                
                logger.info(f"Emergency SOL withdrawal: {result.value}")
                return result.value
            else:
                # Handle SPL token withdrawal
                logger.info(f"Emergency token withdrawal for mint: {token_mint}")
                # Implementation would depend on specific SPL token handling
                return None
                
        except Exception as e:
            logger.error(f"Error in emergency withdrawal: {e}")
            return None
