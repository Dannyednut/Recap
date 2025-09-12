import time
import json
from typing import Dict, List, Any, Optional, Callable
import base64
import asyncio
from solana.rpc.api import Client
from solana.rpc.types import MemcmpOpts
from solana.publickey import PublicKey

from shared.logger import get_logger
from solana_service.engine import SolanaEngine
from solana_service.arbitrage import SolanaArbitrageService

logger = get_logger("SolanaMempoolMonitor")

class SolanaMempoolMonitor:
    """Class for monitoring the Solana mempool for arbitrage opportunities"""
    
    # DEX program IDs to monitor
    MONITORED_PROGRAMS = [
        "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin",  # Serum DEX v3
        "22Y43yTVxuUkoRKdm9thyRhQ3SdgQS7c7kB6UNCiaczD",  # Raydium AMM
        "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium Liquidity Pool
        "DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1"   # Orca Swap
    ]
    
    # Token addresses to monitor (popular tokens on Solana)
    MONITORED_TOKENS = [
        "So11111111111111111111111111111111111111112",  # Wrapped SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",  # BTC (Sollet)
        "2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk",  # ETH (Sollet)
        "AGFEad2et2ZJif9jaGpdMixQqvW5i81aBdvKe7PHNfz3"  # FTT
    ]
    
    def __init__(self, engine: SolanaEngine, arbitrage_service: SolanaArbitrageService):
        """Initialize the mempool monitor
        
        Args:
            engine: SolanaEngine instance for blockchain interaction
            arbitrage_service: SolanaArbitrageService instance for executing arbitrage
        """
        self.engine = engine
        self.client = engine.client
        self.arbitrage_service = arbitrage_service
        
        # Callback for arbitrage opportunities
        self.opportunity_callback = None
        
        # Tracking processed transactions
        self.processed_txs = set()
        self.max_processed_txs = 10000  # Limit to prevent memory issues
        
        # Configuration
        self.min_profit_threshold = 0  # Will be set by user
        self.polling_interval = 0.5  # Seconds between mempool checks
        
        # Last seen signature for transaction history pagination
        self.last_signature = None
        
        logger.info("Solana Mempool Monitor initialized")
    
    def set_opportunity_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback function for when arbitrage opportunities are found
        
        Args:
            callback: Function to call with opportunity details
        """
        self.opportunity_callback = callback
    
    def set_profit_threshold(self, threshold: int) -> None:
        """Set minimum profit threshold for arbitrage opportunities
        
        Args:
            threshold: Minimum profit in lamports
        """
        self.min_profit_threshold = threshold
        logger.info(f"Set profit threshold to {threshold} lamports")
    
    def set_polling_interval(self, interval: float) -> None:
        """Set polling interval for mempool checks
        
        Args:
            interval: Time between checks in seconds
        """
        self.polling_interval = interval
        logger.info(f"Set polling interval to {interval} seconds")
    
    def start_monitoring(self) -> None:
        """Start monitoring the mempool for arbitrage opportunities"""
        logger.info("Starting mempool monitoring")
        
        try:
            # Solana doesn't have a true mempool filter like Ethereum
            # Instead, we poll for recent transactions
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self._monitoring_loop())
        
        except KeyboardInterrupt:
            logger.info("Stopping mempool monitoring")
        except Exception as e:
            logger.error(f"Error in mempool monitoring: {str(e)}")
            raise
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop for polling recent transactions"""
        while True:
            try:
                # Get recent transactions
                recent_txs = await self._get_recent_transactions()
                
                # Process transactions
                for tx in recent_txs:
                    signature = tx.get('signature')
                    
                    # Skip if already processed
                    if signature in self.processed_txs:
                        continue
                    
                    # Add to processed set
                    self.processed_txs.add(signature)
                    
                    # Limit size of processed set
                    if len(self.processed_txs) > self.max_processed_txs:
                        self.processed_txs = set(list(self.processed_txs)[-self.max_processed_txs:])
                    
                    # Process transaction
                    await self._process_transaction(tx)
                
                # Update last signature for pagination
                if recent_txs and len(recent_txs) > 0:
                    self.last_signature = recent_txs[0].get('signature')
                
                # Sleep before next poll
                await asyncio.sleep(self.polling_interval)
            
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(self.polling_interval * 2)  # Back off on error
    
    async def _get_recent_transactions(self) -> List[Dict[str, Any]]:
        """Get recent transactions from the Solana network
        
        Returns:
            List of recent transactions
        """
        # Get recent transactions for monitored programs
        all_txs = []
        
        for program_id in self.MONITORED_PROGRAMS:
            try:
                # Get transactions for this program
                opts = {}
                if self.last_signature:
                    opts['until'] = self.last_signature
                
                response = await self.client.get_signatures_for_address(
                    PublicKey(program_id),
                    limit=20,
                    **opts
                )
                
                if response and 'result' in response:
                    all_txs.extend(response['result'])
            
            except Exception as e:
                logger.error(f"Error getting transactions for program {program_id}: {str(e)}")
        
        # Sort by block time (newest first)
        all_txs.sort(key=lambda tx: tx.get('blockTime', 0), reverse=True)
        
        return all_txs
    
    async def _process_transaction(self, tx_info: Dict[str, Any]) -> None:
        """Process a transaction to check for arbitrage opportunities
        
        Args:
            tx_info: Transaction info from get_signatures_for_address
        """
        try:
            signature = tx_info.get('signature')
            
            # Skip if transaction is not confirmed
            if tx_info.get('confirmationStatus') != 'confirmed':
                return
            
            # Get full transaction details
            response = await self.client.get_transaction(
                signature,
                encoding='jsonParsed'
            )
            
            if not response or 'result' not in response or not response['result']:
                return
            
            tx_data = response['result']
            
            # Check if transaction involves monitored programs
            if not self._is_dex_transaction(tx_data):
                return
            
            # Extract token addresses from transaction
            token_addresses = await self._extract_token_addresses(tx_data)
            
            # Check if any monitored tokens are involved
            if not any(token in self.MONITORED_TOKENS for token in token_addresses):
                return
            
            # Find potential arbitrage opportunities
            opportunities = await self._find_arbitrage_opportunities(tx_data, token_addresses)
            
            # Execute or notify about opportunities
            for opportunity in opportunities:
                if self.opportunity_callback:
                    self.opportunity_callback(opportunity)
                else:
                    await self._execute_arbitrage(opportunity)
        
        except Exception as e:
            logger.error(f"Error processing transaction {tx_info.get('signature')}: {str(e)}")
    
    def _is_dex_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """Check if transaction involves DEX programs
        
        Args:
            tx_data: Transaction data
            
        Returns:
            True if transaction involves DEX programs
        """
        # Check if transaction involves any monitored programs
        if 'transaction' not in tx_data or 'message' not in tx_data['transaction']:
            return False
        
        # Check account keys
        account_keys = tx_data['transaction']['message'].get('accountKeys', [])
        
        for account in account_keys:
            if isinstance(account, dict) and account.get('pubkey') in self.MONITORED_PROGRAMS:
                return True
            elif isinstance(account, str) and account in self.MONITORED_PROGRAMS:
                return True
        
        # Check instructions
        instructions = tx_data['transaction']['message'].get('instructions', [])
        
        for instruction in instructions:
            program_id = instruction.get('programId')
            if program_id in self.MONITORED_PROGRAMS:
                return True
        
        return False
    
    async def _extract_token_addresses(self, tx_data: Dict[str, Any]) -> List[str]:
        """Extract token addresses from transaction data
        
        Args:
            tx_data: Transaction data
            
        Returns:
            List of token addresses
        """
        token_addresses = set()
        
        # Extract from parsed instructions if available
        if 'meta' in tx_data and 'logMessages' in tx_data['meta']:
            for log in tx_data['meta']['logMessages']:
                # Look for token transfer logs
                if 'Transfer' in log and 'amount' in log:
                    # Extract potential token addresses from logs
                    parts = log.split()
                    for part in parts:
                        if len(part) == 44 or len(part) == 43:  # Base58 encoded pubkey length
                            try:
                                # Validate it's a proper pubkey
                                PublicKey(part)
                                token_addresses.add(part)
                            except:
                                pass
        
        # Extract from token balances if available
        if 'meta' in tx_data and 'postTokenBalances' in tx_data['meta']:
            for balance in tx_data['meta']['postTokenBalances']:
                if 'mint' in balance:
                    token_addresses.add(balance['mint'])
        
        # Extract from pre-token balances if available
        if 'meta' in tx_data and 'preTokenBalances' in tx_data['meta']:
            for balance in tx_data['meta']['preTokenBalances']:
                if 'mint' in balance:
                    token_addresses.add(balance['mint'])
        
        return list(token_addresses)
    
    async def _find_arbitrage_opportunities(self, tx_data: Dict[str, Any], token_addresses: List[str]) -> List[Dict[str, Any]]:
        """Find potential arbitrage opportunities based on a transaction
        
        Args:
            tx_data: Transaction data
            token_addresses: List of token addresses involved in the transaction
            
        Returns:
            List of arbitrage opportunities
        """
        # Note: Solana arbitrage is different from EVM chains
        # This is a simplified placeholder implementation
        # In a real implementation, you would need to analyze price impacts
        # across different DEXes and identify profitable paths
        
        opportunities = []
        
        # Get the DEX of the transaction
        dex_program = self._get_dex_from_transaction(tx_data)
        if not dex_program:
            return opportunities
        
        # For each monitored token involved in the transaction
        for token_a in token_addresses:
            if token_a not in self.MONITORED_TOKENS:
                continue
            
            # Check pairs with USDC (common base token)
            usdc_token = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
            
            if token_a != usdc_token:
                # Check for price discrepancies between DEXes
                for dex1 in self.MONITORED_PROGRAMS:
                    if dex1 == dex_program:
                        continue
                    
                    # Check if there's a price difference between DEXes
                    try:
                        # Get price on first DEX
                        price1 = await self.arbitrage_service.get_token_price(
                            token_a, 
                            usdc_token,
                            dex_program
                        )
                        
                        # Get price on second DEX
                        price2 = await self.arbitrage_service.get_token_price(
                            token_a,
                            usdc_token,
                            dex1
                        )
                        
                        # Calculate price difference
                        if price1 > 0 and price2 > 0:
                            price_diff = abs(price1 - price2) / min(price1, price2)
                            
                            # If price difference is significant
                            if price_diff > 0.01:  # 1% difference
                                # Determine direction
                                buy_dex = dex1 if price1 > price2 else dex_program
                                sell_dex = dex_program if price1 > price2 else dex1
                                
                                # Calculate potential profit
                                # This is simplified - in reality you'd need to account for fees and slippage
                                test_amount = 1 * 10**9  # 1 SOL in lamports
                                potential_profit = test_amount * price_diff * 0.95  # Accounting for fees
                                
                                if potential_profit > self.min_profit_threshold:
                                    opportunities.append({
                                        'type': 'cross_dex',
                                        'token_a': token_a,
                                        'token_b': usdc_token,
                                        'buy_dex': buy_dex,
                                        'sell_dex': sell_dex,
                                        'price_diff_percent': price_diff * 100,
                                        'test_amount': test_amount,
                                        'expected_profit': potential_profit
                                    })
                    except Exception as e:
                        logger.debug(f"Error checking price difference: {str(e)}")
        
        return opportunities
    
    async def _execute_arbitrage(self, opportunity: Dict[str, Any]) -> Optional[str]:
        """Execute an arbitrage opportunity
        
        Args:
            opportunity: Arbitrage opportunity details
            
        Returns:
            Transaction signature if executed, None otherwise
        """
        try:
            if opportunity['type'] == 'cross_dex':
                result = await self.arbitrage_service.execute_cross_dex_arbitrage(
                    token_a=opportunity['token_a'],
                    token_b=opportunity['token_b'],
                    buy_dex=opportunity['buy_dex'],
                    sell_dex=opportunity['sell_dex'],
                    amount=opportunity['test_amount'],
                    min_profit=opportunity['expected_profit']
                )
                
                logger.info(f"Executed cross-DEX arbitrage: {result['signature']}")
                return result['signature']
            
            return None
        
        except Exception as e:
            logger.error(f"Error executing arbitrage: {str(e)}")
            return None
    
    def _get_dex_from_transaction(self, tx_data: Dict[str, Any]) -> Optional[str]:
        """Get DEX program ID from transaction data
        
        Args:
            tx_data: Transaction data
            
        Returns:
            DEX program ID or None if not recognized
        """
        if 'transaction' not in tx_data or 'message' not in tx_data['transaction']:
            return None
        
        # Check instructions
        instructions = tx_data['transaction']['message'].get('instructions', [])
        
        for instruction in instructions:
            program_id = instruction.get('programId')
            if program_id in self.MONITORED_PROGRAMS:
                return program_id
        
        # Check account keys
        account_keys = tx_data['transaction']['message'].get('accountKeys', [])
        
        for account in account_keys:
            if isinstance(account, dict) and account.get('pubkey') in self.MONITORED_PROGRAMS:
                return account.get('pubkey')
            elif isinstance(account, str) and account in self.MONITORED_PROGRAMS:
                return account
        
        return None