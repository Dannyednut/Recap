import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Union, List
import json
import base58
from solana.rpc.async_api import AsyncClient
try:
    from solana.keypair import Keypair
    from solana.publickey import PublicKey
    from solana.transaction import Transaction
    from solana.system_program import TransferParams, transfer
except ImportError:
    # Try newer solders import structure
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey as PublicKey
    Transaction = None  # Will need to be implemented
    TransferParams = None
    transfer = None

try:
    from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
except ImportError:
    set_compute_unit_limit = None
    set_compute_unit_price = None
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from interfaces.base_engine import BaseEngine
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
        
    async def initialize(self) -> None:
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
            
        except Exception as e:
            logger.error(f"Failed to initialize Solana engine: {e}")
            raise
    
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
                # SPL Token balance
                # This would require getting token accounts and parsing balances
                # For now, return mock balance
                return Decimal("100.0")  # Mock SPL token balance
                
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
    
    async def execute_transaction(self, transaction_data: Dict[str, Any]) -> str:
        """Execute transaction on Solana"""
        try:
            if not self.keypair or not self.wallet_address:
                raise ValueError("Wallet not initialized")
            
            # This would build and send the actual Solana transaction
            # For now, return mock transaction hash
            mock_signature = "5" + "a" * 87  # 88 character transaction signature
            
            logger.info(f"Solana Transaction sent: {mock_signature}")
            return mock_signature
            
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
            # This would wait for transaction confirmation
            # For now, return mock result
            return {
                "success": True,
                "slot": 150000000,  # Mock slot
                "confirmationStatus": "confirmed"
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
        """Create Jupiter swap instruction"""
        try:
            # This would call Jupiter API to get swap instruction
            # For now, return mock instruction data
            
            mock_instruction = {
                "programId": self.config.JUPITER_V6,
                "keys": [],  # Would contain actual account keys
                "data": "mock_instruction_data"
            }
            
            return {
                "success": True,
                "instruction": mock_instruction,
                "input_amount": amount,
                "output_amount": int(amount * 0.998),  # Mock output with slippage
                "price_impact": 0.1
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
        """Get token price from Jupiter"""
        try:
            # This would call Jupiter price API
            # For now, return mock price based on token pair
            
            if input_mint == self.config.TOKENS["SOL"]:
                if output_mint == self.config.TOKENS["USDC"]:
                    return Decimal("180.50")  # Mock SOL/USDC price
                elif output_mint == self.config.TOKENS["RAY"]:
                    return Decimal("120.0")   # Mock SOL/RAY price
            elif input_mint == self.config.TOKENS["USDC"]:
                if output_mint == self.config.TOKENS["USDT"]:
                    return Decimal("1.001")   # Mock USDC/USDT price
            
            return Decimal("1.0")  # Default fallback
            
        except Exception as e:
            logger.error(f"Error getting Jupiter price: {e}")
            return None
    
    async def shutdown(self) -> None:
        """Shutdown engine"""
        try:
            if self.client:
                await self.client.close()
            logger.info("Solana engine shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down Solana engine: {e}")