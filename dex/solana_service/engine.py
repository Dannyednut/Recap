import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Union, List
import json
import base58
import base64
import aiohttp
import struct
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed
try:
    from solana.keypair import Keypair
    from solana.publickey import PublicKey
    from solana.transaction import Transaction
    from solana.system_program import TransferParams, transfer
    from solana.rpc.api import Client
except ImportError:
    # Try newer solders import structure
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey as PublicKey
    from solders.transaction import VersionedTransaction
    from solders.message import to_bytes_versioned
    Transaction = VersionedTransaction
    TransferParams = None
    transfer = None

try:
    from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
    from solders.instruction import Instruction
except ImportError:
    set_compute_unit_limit = None
    set_compute_unit_price = None
    Instruction = None
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from base_engine import BaseEngine
from models.arbitrage_models import ExecutionResult

from .config import SolanaConfig

logger = logging.getLogger(__name__)

class SolanaEngine(BaseEngine):
    """Solana blockchain engine for RPC operations"""
    
    def __init__(self, config: SolanaConfig):
        self.config = config
        self.client: Optional[AsyncClient] = None
        self.keypair: Optional[Keypair] = None
        self.wallet_address: Optional[str] = None
        
    async def initialize(self) -> bool:
        """Initialize Solana RPC connection and wallet"""
        try:
            # Initialize RPC client
            self.client = AsyncClient(self.config.RPC_URL)
            
            # Initialize wallet
            if self.config.PRIVATE_KEY:
                try:
                    # Try to decode as base58 private key
                    private_key_bytes = base58.b58decode(self.config.PRIVATE_KEY)
                    self.keypair = Keypair.from_secret_key(private_key_bytes)
                except Exception:
                    # Try as JSON array format
                    try:
                        key_array = json.loads(self.config.PRIVATE_KEY)
                        self.keypair = Keypair.from_secret_key(bytes(key_array))
                    except Exception as e:
                        raise ValueError(f"Invalid private key format: {e}")
                
                self.wallet_address = str(self.keypair.public_key)
                logger.info(f"Solana Wallet initialized: {self.wallet_address}")
            
            # Test connection
            result = await self.client.get_health()
            if result.value != "ok":
                logger.warning("Solana RPC health check returned non-OK status")
            
            # Get network info
            genesis_hash = await self.client.get_genesis_hash()
            logger.info(f"Solana engine initialized on network: {self.config.NETWORK}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Solana engine: {e}")
            return False
    
    async def get_balance(self, token_address: str, wallet_address: str = None) -> Decimal:
        """Get token balance for wallet"""
        try:
            target_wallet = wallet_address or self.wallet_address
            if not target_wallet:
                raise ValueError("No wallet address provided")
            
            wallet_pubkey = PublicKey(target_wallet)
            
            # SOL balance
            if token_address.upper() == "SOL" or token_address == self.config.TOKENS["SOL"]:
                balance_result = await self.client.get_balance(wallet_pubkey)
                balance_lamports = balance_result.value
                return Decimal(balance_lamports) / Decimal(self.config.LAMPORTS_PER_SOL)
            else:
                # SPL Token balance - get actual token accounts
                token_accounts = await self.client.get_token_accounts_by_owner(
                    wallet_pubkey,
                    {"mint": PublicKey(token_address)},
                    commitment=Confirmed
                )
                
                total_balance = Decimal("0")
                for account_info in token_accounts.value:
                    # Parse token account data
                    account_data = account_info.account.data
                    if len(account_data) >= 64:  # Standard token account size
                        # Token amount is stored at offset 64-72 (8 bytes, little endian)
                        amount_bytes = account_data[64:72]
                        amount = struct.unpack('<Q', amount_bytes)[0]
                        
                        # Get token decimals
                        decimals = await self._get_token_decimals(token_address)
                        balance = Decimal(amount) / Decimal(10 ** decimals)
                        total_balance += balance
                
                return total_balance
                
        except Exception as e:
            logger.error(f"Error getting Solana balance for {token_address}: {e}")
            return Decimal("0")
    
    async def get_transaction_fee(self, transaction: Transaction) -> int:
        """Get transaction fee in lamports"""
        try:
            # Get recent blockhash and fee calculator
            recent_blockhash = await self.client.get_recent_blockhash()
            
            # Estimate fee based on signatures
            num_signatures = len(transaction.signatures) if hasattr(transaction, 'signatures') else 1
            base_fee = 5000  # Base fee per signature in lamports
            
            # Add compute unit costs
            compute_fee = self.config.COMPUTE_UNIT_PRICE * self.config.MAX_COMPUTE_UNITS // 1_000_000
            
            total_fee = base_fee * num_signatures + compute_fee + self.config.PRIORITY_FEE_LAMPORTS
            
            return total_fee
            
        except Exception as e:
            logger.error(f"Error estimating Solana transaction fee: {e}")
            return 10000  # Fallback fee
    
    async def execute_transaction(self, transaction: Union[Transaction, VersionedTransaction]) -> str:
        """Execute transaction on Solana"""
        try:
            if not self.keypair or not self.wallet_address:
                raise ValueError("Wallet not initialized")
            
            # Sign the transaction
            if hasattr(transaction, 'sign'):
                transaction.sign([self.keypair])
            else:
                # For VersionedTransaction
                transaction.sign([self.keypair])
            
            # Send transaction
            opts = TxOpts(
                skip_preflight=False,
                preflight_commitment=Confirmed,
                max_retries=3
            )
            
            result = await self.client.send_transaction(
                transaction,
                opts=opts
            )
            
            if result.value:
                logger.info(f"Solana Transaction sent: {result.value}")
                return str(result.value)
            else:
                raise Exception("Transaction failed to send")
            
        except Exception as e:
            logger.error(f"Error executing Solana transaction: {e}")
            raise
    
    async def wait_for_transaction_confirmation(
        self, 
        tx_signature: str, 
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Wait for transaction confirmation"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    # Check transaction status
                    result = await self.client.get_signature_statuses([tx_signature])
                    
                    if result.value and len(result.value) > 0:
                        status = result.value[0]
                        if status:
                            if status.confirmation_status == "confirmed" or status.confirmation_status == "finalized":
                                return {
                                    "success": True,
                                    "slot": status.slot,
                                    "confirmationStatus": status.confirmation_status,
                                    "err": status.err
                                }
                            elif status.err:
                                return {
                                    "success": False,
                                    "error": f"Transaction failed: {status.err}",
                                    "slot": status.slot
                                }
                    
                    # Wait before next check
                    await asyncio.sleep(2)
                    
                except Exception as check_error:
                    logger.debug(f"Error checking transaction status: {check_error}")
                    await asyncio.sleep(2)
            
            # Timeout reached
            return {
                "success": False,
                "error": f"Transaction confirmation timeout after {timeout} seconds"
            }
            
        except Exception as e:
            logger.error(f"Error waiting for Solana transaction confirmation: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_current_slot(self) -> int:
        """Get current slot number"""
        try:
            result = await self.client.get_slot()
            return result.value
        except Exception as e:
            logger.error(f"Error getting Solana slot: {e}")
            return 0
    
    async def get_token_accounts(self, wallet_address: str = None) -> List[Dict[str, Any]]:
        """Get all token accounts for wallet"""
        try:
            target_wallet = wallet_address or self.wallet_address
            if not target_wallet:
                raise ValueError("No wallet address provided")
            
            wallet_pubkey = PublicKey(target_wallet)
            
            # Get token accounts by owner
            result = await self.client.get_token_accounts_by_owner(
                wallet_pubkey,
                {"programId": PublicKey("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}  # SPL Token program
            )
            
            token_accounts = []
            for account_info in result.value:
                account_data = account_info.account.data
                # Parse token account data
                token_accounts.append({
                    "pubkey": str(account_info.pubkey),
                    "mint": "unknown",  # Would parse from account data
                    "balance": "0"      # Would parse from account data
                })
            
            return token_accounts
            
        except Exception as e:
            logger.error(f"Error getting Solana token accounts: {e}")
            return []
    
    async def create_jupiter_swap_instruction(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50
    ) -> Dict[str, Any]:
        """Create Jupiter swap instruction using real Jupiter API"""
        try:
            # Get quote from Jupiter
            quote = await self._get_jupiter_quote(
                input_mint, output_mint, amount, slippage_bps
            )
            
            if not quote:
                return {"success": False, "error": "Failed to get Jupiter quote"}
            
            # Get swap instruction from Jupiter
            swap_data = await self._get_jupiter_swap_instruction(
                quote, self.wallet_address
            )
            
            if not swap_data:
                return {"success": False, "error": "Failed to get Jupiter swap instruction"}
            
            return {
                "success": True,
                "swap_transaction": swap_data["swapTransaction"],
                "input_amount": amount,
                "output_amount": int(quote["outAmount"]),
                "price_impact": float(quote.get("priceImpactPct", 0)),
                "route_plan": quote.get("routePlan", [])
            }
            
        except Exception as e:
            logger.error(f"Error creating Jupiter swap instruction: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_token_price_jupiter(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: int = None
    ) -> Optional[Decimal]:
        """Get real token price from Jupiter API"""
        try:
            # Use 1 unit if no amount specified
            if amount is None:
                # Get token decimals to determine 1 unit
                decimals = await self._get_token_decimals(input_mint)
                amount = 10 ** decimals
            
            quote = await self._get_jupiter_quote(input_mint, output_mint, amount)
            
            if quote and "outAmount" in quote:
                input_decimals = await self._get_token_decimals(input_mint)
                output_decimals = await self._get_token_decimals(output_mint)
                
                # Calculate price as output_amount / input_amount
                input_amount_decimal = Decimal(amount) / Decimal(10 ** input_decimals)
                output_amount_decimal = Decimal(quote["outAmount"]) / Decimal(10 ** output_decimals)
                
                if input_amount_decimal > 0:
                    price = output_amount_decimal / input_amount_decimal
                    return price
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting Jupiter price: {e}")
            return None
    
    async def _get_token_decimals(self, mint_address: str) -> int:
        """Get token decimals from mint account"""
        try:
            # Cache common token decimals
            common_decimals = {
                self.config.TOKENS["SOL"]: 9,
                self.config.TOKENS["USDC"]: 6,
                self.config.TOKENS["USDT"]: 6,
                self.config.TOKENS["RAY"]: 6,
                self.config.TOKENS["ORCA"]: 6,
                self.config.TOKENS["SRM"]: 6,
                self.config.TOKENS["BTC"]: 6,
                self.config.TOKENS["ETH"]: 6,
                self.config.TOKENS["BONK"]: 5
            }
            
            if mint_address in common_decimals:
                return common_decimals[mint_address]
            
            # Fetch from blockchain
            mint_info = await self.client.get_account_info(PublicKey(mint_address))
            if mint_info.value and mint_info.value.data:
                # Decimals is at offset 44 in mint account data
                decimals = mint_info.value.data[44]
                return decimals
            
            return 6  # Default fallback
            
        except Exception as e:
            logger.debug(f"Error getting token decimals for {mint_address}: {e}")
            return 6  # Default fallback
    
    async def _get_jupiter_quote(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: int, 
        slippage_bps: int = 50
    ) -> Optional[Dict[str, Any]]:
        """Get quote from Jupiter API"""
        try:
            url = "https://quote-api.jup.ag/v6/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": str(slippage_bps),
                "onlyDirectRoutes": "false",
                "asLegacyTransaction": "false"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"Jupiter quote API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting Jupiter quote: {e}")
            return None
    
    async def _get_jupiter_swap_instruction(
        self, 
        quote: Dict[str, Any], 
        user_public_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get swap instruction from Jupiter API"""
        try:
            url = "https://quote-api.jup.ag/v6/swap"
            payload = {
                "quoteResponse": quote,
                "userPublicKey": user_public_key,
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": self.config.PRIORITY_FEE_LAMPORTS
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"Jupiter swap API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting Jupiter swap instruction: {e}")
            return None
    
    async def execute_jupiter_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50
    ) -> Dict[str, Any]:
        """Execute a swap using Jupiter"""
        try:
            # Get swap instruction
            swap_result = await self.create_jupiter_swap_instruction(
                input_mint, output_mint, amount, slippage_bps
            )
            
            if not swap_result["success"]:
                return swap_result
            
            # Deserialize and execute transaction
            swap_transaction_b64 = swap_result["swap_transaction"]
            swap_transaction_bytes = base64.b64decode(swap_transaction_b64)
            
            # Create transaction from bytes
            if Transaction:
                transaction = Transaction.deserialize(swap_transaction_bytes)
            else:
                transaction = VersionedTransaction.from_bytes(swap_transaction_bytes)
            
            # Execute transaction
            tx_signature = await self.execute_transaction(transaction)
            
            # Wait for confirmation
            confirmation = await self.wait_for_transaction_confirmation(tx_signature)
            
            return {
                "success": confirmation["success"],
                "tx_signature": tx_signature,
                "input_amount": amount,
                "output_amount": swap_result["output_amount"],
                "price_impact": swap_result["price_impact"],
                "confirmation": confirmation
            }
            
        except Exception as e:
            logger.error(f"Error executing Jupiter swap: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def shutdown(self) -> None:
        """Shutdown engine"""
        try:
            if self.client:
                await self.client.close()
            logger.info("Solana engine shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down Solana engine: {e}")