import os
import asyncio
import logging
from typing import Dict, Any, Optional
from web3 import AsyncWeb3
from web3.contract import AsyncContract
from eth_account import Account
from eth_account.signers.local import LocalAccount
import json
import os
from ..shared.mev_protection import UniversalMEVProtection
from .engine import PolygonEngine
from .config import PolygonConfig

logger = logging.getLogger(__name__)

class PolygonContractExecutor:
    """Class for executing arbitrage contracts on Polygon network"""
    
    # Polygon DEX router addresses
    QUICKSWAP_V2_ROUTER = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"
    QUICKSWAP_V3_ROUTER = "0xf5b509bB0909a69B1c207E495f687a596C168E12"
    SUSHISWAP_ROUTER = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
    UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
    
    # Flash loan providers on Polygon
    AAVE_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
    
    def __init__(self, engine: PolygonEngine, config: PolygonConfig):
        """Initialize the contract executor with the Polygon engine
        
        Args:
            engine: PolygonEngine instance for blockchain interaction
            config: PolygonConfig instance for configuration
        """
        self.engine = engine
        self.config = config
        self.w3 = engine.w3
        self.account = engine.account
        self.wallet_address = engine.wallet_address
        
        # MEV Protection for Polygon (chain_id = 137)
        self.mev_protection = UniversalMEVProtection(
            chain_id=137,
            w3=self.w3,
            private_key=config.PRIVATE_KEY
        )
        
        # Router addresses mapping
        self.routers = {
            "quickswap_v2": self.QUICKSWAP_V2_ROUTER,
            "quickswap_v3": self.QUICKSWAP_V3_ROUTER,
            "sushiswap": self.SUSHISWAP_ROUTER,
            "uniswap_v3": self.UNISWAP_V3_ROUTER
        }
        
        # Flash loan providers mapping
        self.flash_loan_providers = {
            "aave": self.AAVE_POOL
        }
        
        # Load contract ABIs
        from ..shared.utils import load_contract_abi
        self.arbitrage_executor_abi = load_contract_abi("PolygonArbitrageExecutor")
        
        # Contract instances
        self.arbitrage_executor_address = None
        self.arbitrage_executor_contract = None
        
        # Deployment info file
        self.deployment_file_path = os.path.join(
            os.path.dirname(__file__), 'deployed_contracts.json'
        )
    
    async def initialize(self):
        """Initialize the contract executor"""
        logger.info("Initializing Polygon contract executor...")
        
        # Check if arbitrage executor is deployed
        await self._load_or_deploy_arbitrage_executor()
        
        logger.info("Polygon contract executor initialized")
    
    async def _load_or_deploy_arbitrage_executor(self):
        """Load existing arbitrage executor or deploy a new one"""
        try:
            # Try to load from deployment file
            if os.path.exists(self.deployment_file_path):
                with open(self.deployment_file_path, 'r') as f:
                    deployment_data = json.load(f)
                    
                if "polygon_arbitrage_executor" in deployment_data:
                    address = deployment_data["polygon_arbitrage_executor"]
                    logger.info(f"Loading PolygonArbitrageExecutor from {address}")
                    
                    # Verify contract exists on chain
                    code = await self.w3.eth.get_code(address)
                    if len(code) > 0:
                        self.arbitrage_executor_address = self.w3.to_checksum_address(address)
                        self.arbitrage_executor_contract = self.w3.eth.contract(
                            address=self.arbitrage_executor_address,
                            abi=self.arbitrage_executor_abi
                        )
                        return
                    else:
                        logger.warning(f"Contract at {address} has no code, redeploying")
            
            # If not found, deploy a new one
            logger.info("Deploying new PolygonArbitrageExecutor contract...")
            await self._deploy_arbitrage_executor()
            
        except Exception as e:
            logger.error(f"Error loading/deploying Polygon arbitrage executor: {e}")
            raise
    
    def load_arbitrage_executor(self, address: str) -> None:
        """Load an existing arbitrage executor contract
        
        Args:
            address: Address of the deployed contract
        """
        self.arbitrage_executor_address = self.w3.to_checksum_address(address)
        self.arbitrage_executor_contract = self.w3.eth.contract(
            address=self.arbitrage_executor_address,
            abi=self.arbitrage_executor_abi
        )
        logger.info(f"Loaded arbitrage executor contract at {address}")
    
    async def _deploy_arbitrage_executor(self) -> str:
        """Deploy a new arbitrage executor contract using the contract deployer
        
        Returns:
            str: Address of the deployed contract
        """
        try:
            # Use the contract deployer to deploy arbitrage contract
            from .contracts.deploy import PolygonContractDeployer
            
            deployer = PolygonContractDeployer(self.w3, self.engine.config.PRIVATE_KEY)
            await deployer.initialize()
            
            # Deploy the contract
            result = await deployer.deploy_arbitrage_contract()
            
            if result['success']:
                contract_address = result['contract_address']
                
                # Save deployment info
                deployment_data = {}
                if os.path.exists(self.deployment_file_path):
                    with open(self.deployment_file_path, 'r') as f:
                        deployment_data = json.load(f)
                
                deployment_data["polygon_arbitrage_executor"] = contract_address
                
                with open(self.deployment_file_path, 'w') as f:
                    json.dump(deployment_data, f, indent=2)
                
                # Set contract address and instance
                self.arbitrage_executor_address = self.w3.to_checksum_address(contract_address)
                self.arbitrage_executor_contract = self.w3.eth.contract(
                    address=self.arbitrage_executor_address,
                    abi=self.arbitrage_executor_abi
                )
                
                logger.info(f"Deployed arbitrage executor contract at {contract_address}")
                return contract_address
            else:
                raise Exception(f"Contract deployment failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error deploying Polygon arbitrage executor: {e}")
            raise
    
    def deploy_arbitrage_executor(self) -> str:
        """Deploy a new arbitrage executor contract (synchronous wrapper)
        
        Returns:
            str: Address of the deployed contract
        """
        import asyncio
        return asyncio.run(self._deploy_arbitrage_executor())
    
    def execute_cross_exchange_arbitrage(
        self,
        token_a: str,
        token_b: str,
        amount_in: int,
        buy_dex: str,
        sell_dex: str,
        buy_fee: int = 3000,  # Default fee for V3 pools
        sell_fee: int = 3000,  # Default fee for V3 pools
        use_flash_loan: bool = False,
        flash_loan_provider: str = "aave",
        min_profit: int = 0
    ) -> Dict[str, Any]:
        """Execute cross-exchange arbitrage between two DEXes
        
        Args:
            token_a: Address of the input token
            token_b: Address of the output token
            amount_in: Amount of token_a to trade
            buy_dex: DEX to buy token_b (quickswap_v2, quickswap_v3, sushiswap, uniswap_v3)
            sell_dex: DEX to sell token_b (quickswap_v2, quickswap_v3, sushiswap, uniswap_v3)
            buy_fee: Fee tier for V3 pools (only for V3 DEXes)
            sell_fee: Fee tier for V3 pools (only for V3 DEXes)
            use_flash_loan: Whether to use flash loan
            flash_loan_provider: Flash loan provider to use (aave)
            min_profit: Minimum profit required
            
        Returns:
            Dict with transaction details and profit information
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Get router addresses
        buy_router = self.routers.get(buy_dex)
        sell_router = self.routers.get(sell_dex)
        
        if not buy_router or not sell_router:
            raise ValueError(f"Invalid DEX specified: {buy_dex} or {sell_dex}")
        
        # Get flash loan provider address if using flash loan
        flash_loan_provider_address = self.flash_loan_providers.get(flash_loan_provider) if use_flash_loan else "0x0000000000000000000000000000000000000000"
        
        # Prepare transaction parameters
        params = {
            'tokenA': self.w3.to_checksum_address(token_a),
            'tokenB': self.w3.to_checksum_address(token_b),
            'amountIn': amount_in,
            'buyRouter': buy_router,
            'sellRouter': sell_router,
            'buyFee': buy_fee,
            'sellFee': sell_fee,
            'useFlashLoan': use_flash_loan,
            'flashLoanProvider': flash_loan_provider_address,
            'minProfit': min_profit
        }
        
        # Estimate gas
        gas_estimate = self.arbitrage_executor_contract.functions.executeArbitrage(params).estimate_gas({
            'from': self.engine.account.address
        })
        
        # Execute transaction
        tx_hash = self.arbitrage_executor_contract.functions.executeArbitrage(params).transact({
            'from': self.engine.account.address,
            'gas': int(gas_estimate * 1.2)  # Add 20% buffer
        })
        
        # Wait for transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Parse events to get profit information
        profit_info = self._parse_arbitrage_events(tx_receipt)
        
        return {
            'tx_hash': tx_hash.hex(),
            'gas_used': tx_receipt.gasUsed,
            'status': tx_receipt.status,
            'profit_info': profit_info
        }
    
    async def execute_triangular_arbitrage(
        self,
        path: List[str],
        routers: List[str],
        fees: List[int],
        amount_in: int,
        min_profit: int = 0,
        use_flash_loan: bool = False,
        flash_loan_provider: str = "aave"
    ) -> Dict[str, Any]:
        """Execute triangular arbitrage across multiple DEXes
        
        Args:
            path: List of token addresses in the triangular path
            routers: List of router names for each hop
            fees: List of fee tiers for each hop (for V3 pools)
            amount_in: Amount of the first token to trade
            min_profit: Minimum profit required
            use_flash_loan: Whether to use flash loan
            flash_loan_provider: Flash loan provider to use
            
        Returns:
            Dict with transaction details and profit information
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Convert router names to addresses
        router_addresses = [self.routers.get(router) for router in routers]
        if None in router_addresses:
            raise ValueError(f"Invalid router in: {routers}")
        
        # Get flash loan provider address if using flash loan
        flash_loan_provider_address = self.flash_loan_providers.get(flash_loan_provider) if use_flash_loan else "0x0000000000000000000000000000000000000000"
        
        # Convert token addresses to checksum format
        path_addresses = [Web3.to_checksum_address(token) for token in path]
        
        # Prepare transaction parameters
        params = {
            'path': path_addresses,
            'routers': router_addresses,
            'fees': fees,
            'amountIn': amount_in,
            'minProfitAmount': min_profit,
            'flashLoanProvider': flash_loan_provider_address
        }
        
        # Estimate gas
        gas_estimate = self.arbitrage_executor_contract.functions.executeTriangularArbitrage(params).estimate_gas({
            'from': self.engine.account.address
        })
        
        # Build transaction
        tx = self.arbitrage_executor_contract.functions.executeTriangularArbitrage(params).build_transaction({
            'from': self.wallet_address,
            'gas': int(gas_estimate * 1.2),
            'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
        })
        
        # Check if MEV protection should be used
        if params.get("useMEVProtection", True):
            current_block = await self.w3.eth.block_number
            target_block = current_block + 1
            
            signed_tx = self.account.sign_transaction(tx)
            tx_data = {
                "raw_tx": signed_tx.rawTransaction.hex(),
                "priority_fee": tx.get("maxPriorityFeePerGas", 2000000000),
                "max_fee": tx.get("maxFeePerGas", 50000000000)
            }
            
            bundle_hash = await self.mev_protection.submit_arbitrage_bundle(
                [tx_data], target_block
            )
            
            if bundle_hash:
                logger.info(f"Polygon triangular arbitrage bundle submitted via MEV protection: {bundle_hash}")
                return {'tx_hash': bundle_hash, 'status': 'submitted_via_mev'}
            else:
                logger.warning("Polygon MEV protection failed, falling back to mempool")
        
        # Fallback to standard mempool submission
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for transaction receipt
        tx_receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Parse events to get profit information
        profit_info = self._parse_arbitrage_events(tx_receipt)
        
        return {
            'tx_hash': tx_hash.hex(),
            'gas_used': tx_receipt.gasUsed,
            'status': tx_receipt.status,
            'profit_info': profit_info
        }
    
    async def execute_backrun_arbitrage(
        self,
        target_tx_hash: str,
        path: List[str],
        routers: List[str],
        fees: List[int],
        amount_in: int,
        min_profit: int = 0,
        max_gas_price: int = None,
        use_flash_loan: bool = False,
        flash_loan_provider: str = "aave"
    ) -> Dict[str, Any]:
        """Execute backrun arbitrage after a specific transaction
        
        Args:
            target_tx_hash: Transaction hash to backrun
            path: List of token addresses in the path
            routers: List of router names for each hop
            fees: List of fee tiers for each hop (for V3 pools)
            amount_in: Amount of the first token to trade
            min_profit: Minimum profit required
            max_gas_price: Maximum gas price to use
            use_flash_loan: Whether to use flash loan
            flash_loan_provider: Flash loan provider to use
            
        Returns:
            Dict with transaction details and profit information
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Convert router names to addresses
        router_addresses = [self.routers.get(router) for router in routers]
        if None in router_addresses:
            raise ValueError(f"Invalid router in: {routers}")
        
        # Get flash loan provider address if using flash loan
        flash_loan_provider_address = self.flash_loan_providers.get(flash_loan_provider) if use_flash_loan else "0x0000000000000000000000000000000000000000"
        
        # Convert token addresses to checksum format
        path_addresses = [Web3.to_checksum_address(token) for token in path]
        
        # Set max gas price if not provided
        if max_gas_price is None:
            max_gas_price = self.w3.eth.gas_price * 2  # Default to 2x current gas price
        
        # Prepare transaction parameters
        params = {
            'targetTxHash': self.w3.to_bytes(hexstr=target_tx_hash),
            'path': path_addresses,
            'routers': router_addresses,
            'fees': fees,
            'amountIn': amount_in,
            'minProfitAmount': min_profit,
            'flashLoanProvider': flash_loan_provider_address,
            'maxGasPrice': max_gas_price
        }
        
        # Estimate gas
        gas_estimate = self.arbitrage_executor_contract.functions.executeBackrunArbitrage(params).estimate_gas({
            'from': self.engine.account.address
        })
        
        # Execute transaction
        tx_hash = self.arbitrage_executor_contract.functions.executeBackrunArbitrage(params).transact({
            'from': self.engine.account.address,
            'gas': int(gas_estimate * 1.2),  # Add 20% buffer
            'gasPrice': max_gas_price
        })
        
        # Wait for transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Parse events to get profit information
        profit_info = self._parse_arbitrage_events(tx_receipt)
        
        return {
            'tx_hash': tx_hash.hex(),
            'gas_used': tx_receipt.gasUsed,
            'status': tx_receipt.status,
            'profit_info': profit_info
        }
    
    def emergency_withdraw(self, token_address: str) -> Dict[str, Any]:
        """Emergency withdraw function to recover stuck tokens
        
        Args:
            token_address: Address of the token to withdraw
            
        Returns:
            Dict with transaction details
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Execute transaction
        tx_hash = self.arbitrage_executor_contract.functions.emergencyWithdraw(
            self.w3.to_checksum_address(token_address)
        ).transact({
            'from': self.engine.account.address
        })
        
        # Wait for transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {
            'tx_hash': tx_hash.hex(),
            'gas_used': tx_receipt.gasUsed,
            'status': tx_receipt.status
        }
    
    def get_arbitrage_quote(
        self,
        token_a: str,
        token_b: str,
        amount_in: int,
        buy_dex: str,
        sell_dex: str,
        buy_fee: int = 3000,
        sell_fee: int = 3000
    ) -> Dict[str, Any]:
        """Get arbitrage quote for a given pair of tokens and DEXes
        
        Args:
            token_a: Address of the input token
            token_b: Address of the output token
            amount_in: Amount of token_a to trade
            buy_dex: DEX to buy token_b
            sell_dex: DEX to sell token_b
            buy_fee: Fee tier for V3 pools
            sell_fee: Fee tier for V3 pools
            
        Returns:
            Dict with quote information
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Get router addresses
        buy_router = self.routers.get(buy_dex)
        sell_router = self.routers.get(sell_dex)
        
        if not buy_router or not sell_router:
            raise ValueError(f"Invalid DEX specified: {buy_dex} or {sell_dex}")
        
        # Call contract function
        result = self.arbitrage_executor_contract.functions.getArbitrageQuote(
            self.w3.to_checksum_address(token_a),
            self.w3.to_checksum_address(token_b),
            amount_in,
            buy_router,
            sell_router,
            buy_fee,
            sell_fee
        ).call()
        
        # Parse result
        buy_amount, sell_amount, profit = result
        
        return {
            'buy_amount': buy_amount,
            'sell_amount': sell_amount,
            'profit': profit,
            'is_profitable': profit > 0
        }
    
    def get_triangular_arbitrage_quote(
        self,
        path: List[str],
        routers: List[str],
        fees: List[int],
        amount_in: int
    ) -> Dict[str, Any]:
        """Get triangular arbitrage quote for a given path of tokens and DEXes
        
        Args:
            path: List of token addresses in the triangular path
            routers: List of router names for each hop
            fees: List of fee tiers for each hop (for V3 pools)
            amount_in: Amount of the first token to trade
            
        Returns:
            Dict with quote information
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Convert router names to addresses
        router_addresses = [self.routers.get(router) for router in routers]
        if None in router_addresses:
            raise ValueError(f"Invalid router in: {routers}")
        
        # Convert token addresses to checksum format
        path_addresses = [Web3.to_checksum_address(token) for token in path]
        
        # Call contract function
        result = self.arbitrage_executor_contract.functions.getTriangularArbitrageQuote(
            path_addresses,
            router_addresses,
            fees,
            amount_in
        ).call()
        
        # Parse result
        final_amount, profit = result
        
        return {
            'final_amount': final_amount,
            'profit': profit,
            'is_profitable': profit > 0
        }
    
    def get_backrun_arbitrage_quote(
        self,
        path: List[str],
        routers: List[str],
        fees: List[int],
        amount_in: int
    ) -> Dict[str, Any]:
        """Get backrun arbitrage quote for a given path of tokens and DEXes
        
        Args:
            path: List of token addresses in the path
            routers: List of router names for each hop
            fees: List of fee tiers for each hop (for V3 pools)
            amount_in: Amount of the first token to trade
            
        Returns:
            Dict with quote information
        """
        if self.arbitrage_executor_contract is None:
            raise ValueError("Arbitrage executor contract not loaded")
        
        # Convert router names to addresses
        router_addresses = [self.routers.get(router) for router in routers]
        if None in router_addresses:
            raise ValueError(f"Invalid router in: {routers}")
        
        # Convert token addresses to checksum format
        path_addresses = [Web3.to_checksum_address(token) for token in path]
        
        # Call contract function
        result = self.arbitrage_executor_contract.functions.getBackrunArbitrageQuote(
            path_addresses,
            router_addresses,
            fees,
            amount_in
        ).call()
        
        # Parse result
        final_amount, profit = result
        
        return {
            'final_amount': final_amount,
            'profit': profit,
            'is_profitable': profit > 0
        }
    
    def _parse_arbitrage_events(self, tx_receipt) -> Dict[str, Any]:
        """Parse arbitrage events from transaction receipt
        
        Args:
            tx_receipt: Transaction receipt
            
        Returns:
            Dict with profit information
        """
        # Initialize result
        result = {
            'profit': 0,
            'token_in': None,
            'token_out': None,
            'amount_in': 0,
            'buy_dex': None,
            'sell_dex': None
        }
        
        # Check if contract is loaded
        if self.arbitrage_executor_contract is None:
            return result
        
        # Parse ArbitrageExecuted events
        arbitrage_event = self.arbitrage_executor_contract.events.ArbitrageExecuted()
        arbitrage_logs = arbitrage_event.process_receipt(tx_receipt)
        
        if arbitrage_logs:
            log = arbitrage_logs[0]
            result['token_in'] = log['args']['tokenIn']
            result['token_out'] = log['args']['tokenOut']
            result['amount_in'] = log['args']['amountIn']
            result['profit'] = log['args']['profit']
            result['buy_dex'] = log['args']['buyDex']
            result['sell_dex'] = log['args']['sellDex']
        
        # Parse FlashLoanExecuted events
        flash_loan_event = self.arbitrage_executor_contract.events.FlashLoanExecuted()
        flash_loan_logs = flash_loan_event.process_receipt(tx_receipt)
        
        if flash_loan_logs:
            log = flash_loan_logs[0]
            # Update profit if flash loan was used
            result['flash_loan_asset'] = log['args']['asset']
            result['flash_loan_amount'] = log['args']['amount']
            result['profit'] = log['args']['profit']
        
        return result