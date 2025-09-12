import time
import json
from typing import Dict, List, Any, Optional, Callable
from web3 import Web3
from web3.types import TxReceipt
from hexbytes import HexBytes

from shared.logger import get_logger
from bsc_service.engine import BSCEngine
from bsc_service.contract_executor import BSCContractExecutor

logger = get_logger("BSCMempoolMonitor")

class BSCMempoolMonitor:
    """Class for monitoring the BSC mempool for arbitrage opportunities"""
    
    # DEX router addresses to monitor
    MONITORED_ADDRESSES = [
        "0x10ED43C718714eb63d5aA57B78B54704E256024E",  # PancakeSwap V2
        "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",  # PancakeSwap V3
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",  # SushiSwap
        "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8"   # BiSwap
    ]
    
    # Token addresses to monitor (popular tokens on BSC)
    MONITORED_TOKENS = [
        "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
        "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",  # BUSD
        "0x55d398326f99059fF775485246999027B3197955",  # USDT
        "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",  # USDC
        "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",  # BTCB
        "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"   # ETH
    ]
    
    def __init__(self, engine: BSCEngine, contract_executor: BSCContractExecutor):
        """Initialize the mempool monitor
        
        Args:
            engine: BSCEngine instance for blockchain interaction
            contract_executor: BSCContractExecutor instance for executing arbitrage
        """
        self.engine = engine
        self.w3 = engine.w3
        self.contract_executor = contract_executor
        
        # Set up pending transaction filter
        self.tx_filter = self.w3.eth.filter('pending')
        
        # Callback for arbitrage opportunities
        self.opportunity_callback = None
        
        # Tracking processed transactions
        self.processed_txs = set()
        self.max_processed_txs = 10000  # Limit to prevent memory issues
        
        # Configuration
        self.min_profit_threshold = 0  # Will be set by user
        self.gas_price_multiplier = 1.1  # 10% higher than target tx
        self.max_gas_price = None  # Will be set by user
        
        logger.info("BSC Mempool Monitor initialized")
    
    def set_opportunity_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback function for when arbitrage opportunities are found
        
        Args:
            callback: Function to call with opportunity details
        """
        self.opportunity_callback = callback
    
    def set_profit_threshold(self, threshold: int) -> None:
        """Set minimum profit threshold for arbitrage opportunities
        
        Args:
            threshold: Minimum profit in wei
        """
        self.min_profit_threshold = threshold
        logger.info(f"Set profit threshold to {threshold} wei")
    
    def set_max_gas_price(self, max_gas_price: int) -> None:
        """Set maximum gas price for backrun transactions
        
        Args:
            max_gas_price: Maximum gas price in wei
        """
        self.max_gas_price = max_gas_price
        logger.info(f"Set max gas price to {max_gas_price} wei")
    
    def start_monitoring(self, polling_interval: float = 0.1) -> None:
        """Start monitoring the mempool for arbitrage opportunities
        
        Args:
            polling_interval: Time between polling for new transactions (seconds)
        """
        logger.info("Starting mempool monitoring")
        
        try:
            while True:
                # Get new pending transactions
                pending_txs = self.tx_filter.get_new_entries()
                
                for tx_hash in pending_txs:
                    # Skip if already processed
                    if tx_hash in self.processed_txs:
                        continue
                    
                    # Add to processed set
                    self.processed_txs.add(tx_hash)
                    
                    # Limit size of processed set
                    if len(self.processed_txs) > self.max_processed_txs:
                        self.processed_txs = set(list(self.processed_txs)[-self.max_processed_txs:])
                    
                    # Process transaction
                    self._process_transaction(tx_hash)
                
                # Sleep before next poll
                time.sleep(polling_interval)
        
        except KeyboardInterrupt:
            logger.info("Stopping mempool monitoring")
        except Exception as e:
            logger.error(f"Error in mempool monitoring: {str(e)}")
            raise
    
    def _process_transaction(self, tx_hash: HexBytes) -> None:
        """Process a pending transaction to check for arbitrage opportunities
        
        Args:
            tx_hash: Hash of the pending transaction
        """
        try:
            # Get transaction details
            tx = self.w3.eth.get_transaction(tx_hash)
            
            # Skip if transaction is None (already mined or dropped)
            if tx is None:
                return
            
            # Check if transaction is to a monitored address
            if tx.get('to') not in self.MONITORED_ADDRESSES:
                return
            
            # Decode transaction input data
            input_data = tx.get('input', '0x')
            
            # Check for swap functions (common in DEX routers)
            if not (input_data.startswith('0x38ed1739') or  # swapExactTokensForTokens
                    input_data.startswith('0x8803dbee') or  # swapTokensForExactTokens
                    input_data.startswith('0x7ff36ab5') or  # swapExactETHForTokens
                    input_data.startswith('0x4a25d94a') or  # swapTokensForExactETH
                    input_data.startswith('0x18cbafe5') or  # swapExactTokensForETH
                    input_data.startswith('0xfb3bdb41') or  # swapETHForExactTokens
                    input_data.startswith('0x5c11d795') or  # exactInputSingle (V3)
                    input_data.startswith('0xc04b8d59')):    # exactInput (V3)
                return
            
            # Extract token addresses from input data (simplified)
            # In a real implementation, you would need to properly decode the ABI
            # This is a placeholder for demonstration
            token_addresses = self._extract_token_addresses(input_data)
            
            # Check if any monitored tokens are involved
            if not any(token in self.MONITORED_TOKENS for token in token_addresses):
                return
            
            # Find potential arbitrage opportunities
            opportunities = self._find_arbitrage_opportunities(tx, token_addresses)
            
            # Execute or notify about opportunities
            for opportunity in opportunities:
                if self.opportunity_callback:
                    self.opportunity_callback(opportunity)
                else:
                    self._execute_arbitrage(opportunity)
        
        except Exception as e:
            logger.error(f"Error processing transaction {tx_hash.hex()}: {str(e)}")
    
    def _extract_token_addresses(self, input_data: str) -> List[str]:
        """Extract token addresses from transaction input data
        
        Args:
            input_data: Transaction input data
            
        Returns:
            List of token addresses
        """
        # This is a simplified placeholder implementation
        # In a real implementation, you would need to properly decode the ABI
        # based on the function signature
        
        # For demonstration purposes, we'll just extract potential addresses
        # from the input data at common offsets
        addresses = []
        
        # Skip function signature (4 bytes) and look for potential addresses
        data = input_data[10:]
        
        # Look for potential addresses in the data
        # Addresses are 20 bytes (40 hex chars) and typically appear at specific offsets
        # This is a very simplified approach and would need to be improved
        for i in range(0, len(data) - 40, 2):
            potential_address = '0x' + data[i:i+40]
            if Web3.is_address(potential_address):
                addresses.append(Web3.to_checksum_address(potential_address))
        
        return addresses
    
    def _find_arbitrage_opportunities(self, tx: Dict[str, Any], token_addresses: List[str]) -> List[Dict[str, Any]]:
        """Find potential arbitrage opportunities based on a pending transaction
        
        Args:
            tx: Transaction details
            token_addresses: List of token addresses involved in the transaction
            
        Returns:
            List of arbitrage opportunities
        """
        opportunities = []
        
        # Get the DEX of the pending transaction
        target_dex = self._get_dex_from_address(tx.get('to'))
        if not target_dex:
            return opportunities
        
        # Get gas price for backrun
        gas_price = int(tx.get('gasPrice', 0) * self.gas_price_multiplier)
        if self.max_gas_price and gas_price > self.max_gas_price:
            gas_price = self.max_gas_price
        
        # Check for triangular arbitrage opportunities
        for token_a in token_addresses:
            if token_a not in self.MONITORED_TOKENS:
                continue
            
            # Check triangular paths with common base tokens
            for token_b in self.MONITORED_TOKENS:
                if token_b == token_a:
                    continue
                
                for token_c in self.MONITORED_TOKENS:
                    if token_c == token_a or token_c == token_b:
                        continue
                    
                    # Check different DEX combinations
                    for dex1 in ['pancakeswap_v2', 'pancakeswap_v3', 'sushiswap', 'biswap']:
                        for dex2 in ['pancakeswap_v2', 'pancakeswap_v3', 'sushiswap', 'biswap']:
                            if dex1 == dex2:
                                continue
                            
                            for dex3 in ['pancakeswap_v2', 'pancakeswap_v3', 'sushiswap', 'biswap']:
                                if dex3 == dex1 or dex3 == dex2:
                                    continue
                                
                                # Create path and routers
                                path = [token_a, token_b, token_c, token_a]
                                routers = [dex1, dex2, dex3]
                                fees = [3000, 3000, 3000]  # Default fees for V3 pools
                                
                                # Check if profitable
                                try:
                                    # Use a test amount (e.g., 1 WBNB)
                                    test_amount = 1 * 10**18
                                    
                                    quote = self.contract_executor.get_triangular_arbitrage_quote(
                                        path=path,
                                        routers=routers,
                                        fees=fees,
                                        amount_in=test_amount
                                    )
                                    
                                    if quote['is_profitable'] and quote['profit'] > self.min_profit_threshold:
                                        opportunities.append({
                                            'type': 'triangular',
                                            'target_tx_hash': tx.get('hash').hex(),
                                            'path': path,
                                            'routers': routers,
                                            'fees': fees,
                                            'amount_in': test_amount,
                                            'expected_profit': quote['profit'],
                                            'gas_price': gas_price
                                        })
                                except Exception as e:
                                    logger.debug(f"Error checking triangular arbitrage: {str(e)}")
        
        # Check for backrun arbitrage opportunities
        for token_a in token_addresses:
            if token_a not in self.MONITORED_TOKENS:
                continue
            
            # Check different pairs with token_a
            for token_b in self.MONITORED_TOKENS:
                if token_b == token_a:
                    continue
                
                # Check different DEX combinations
                for dex1 in ['pancakeswap_v2', 'pancakeswap_v3', 'sushiswap', 'biswap']:
                    if dex1 == target_dex:
                        continue
                    
                    # Create path and routers
                    path = [token_a, token_b, token_a]
                    routers = [dex1, target_dex]
                    fees = [3000, 3000]  # Default fees for V3 pools
                    
                    # Check if profitable
                    try:
                        # Use a test amount (e.g., 1 WBNB)
                        test_amount = 1 * 10**18
                        
                        quote = self.contract_executor.get_backrun_arbitrage_quote(
                            path=path,
                            routers=routers,
                            fees=fees,
                            amount_in=test_amount
                        )
                        
                        if quote['is_profitable'] and quote['profit'] > self.min_profit_threshold:
                            opportunities.append({
                                'type': 'backrun',
                                'target_tx_hash': tx.get('hash').hex(),
                                'path': path,
                                'routers': routers,
                                'fees': fees,
                                'amount_in': test_amount,
                                'expected_profit': quote['profit'],
                                'gas_price': gas_price,
                                'max_gas_price': self.max_gas_price or gas_price * 2
                            })
                    except Exception as e:
                        logger.debug(f"Error checking backrun arbitrage: {str(e)}")
        
        return opportunities
    
    def _execute_arbitrage(self, opportunity: Dict[str, Any]) -> Optional[str]:
        """Execute an arbitrage opportunity
        
        Args:
            opportunity: Arbitrage opportunity details
            
        Returns:
            Transaction hash if executed, None otherwise
        """
        try:
            if opportunity['type'] == 'triangular':
                result = self.contract_executor.execute_triangular_arbitrage(
                    path=opportunity['path'],
                    routers=opportunity['routers'],
                    fees=opportunity['fees'],
                    amount_in=opportunity['amount_in'],
                    min_profit=opportunity['expected_profit']
                )
                
                logger.info(f"Executed triangular arbitrage: {result['tx_hash']}")
                return result['tx_hash']
                
            elif opportunity['type'] == 'backrun':
                result = self.contract_executor.execute_backrun_arbitrage(
                    target_tx_hash=opportunity['target_tx_hash'],
                    path=opportunity['path'],
                    routers=opportunity['routers'],
                    fees=opportunity['fees'],
                    amount_in=opportunity['amount_in'],
                    min_profit=opportunity['expected_profit'],
                    max_gas_price=opportunity['max_gas_price']
                )
                
                logger.info(f"Executed backrun arbitrage: {result['tx_hash']}")
                return result['tx_hash']
            
            return None
        
        except Exception as e:
            logger.error(f"Error executing arbitrage: {str(e)}")
            return None
    
    def _get_dex_from_address(self, address: str) -> Optional[str]:
        """Get DEX name from router address
        
        Args:
            address: Router address
            
        Returns:
            DEX name or None if not recognized
        """
        if not address:
            return None
        
        address = Web3.to_checksum_address(address)
        
        dex_mapping = {
            "0x10ED43C718714eb63d5aA57B78B54704E256024E": "pancakeswap_v2",
            "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4": "pancakeswap_v3",
            "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "sushiswap",
            "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8": "biswap"
        }
        
        return dex_mapping.get(address)