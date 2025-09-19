"""
Smart contract execution interface for BSC arbitrage
"""
import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from web3 import AsyncWeb3
from web3.contract import AsyncContract
from eth_account import Account
from eth_account.signers.local import LocalAccount
import os

from .engine import BSCEngine
from .config import BSCConfig
from ..shared.mev_protection import UniversalMEVProtection
from ..shared.contract_addresses import get_chain_addresses, get_router_address
from ..shared.abi_fetcher import ABIFetcher, FALLBACK_ABIS

logger = logging.getLogger(__name__)

class BSCContractExecutor:
    """Execute arbitrage opportunities using smart contracts on BSC"""
    
    def __init__(self, engine: BSCEngine, config: BSCConfig):
        self.engine = engine
        self.config = config
        self.w3 = engine.w3
        self.account = engine.account
        self.wallet_address = engine.wallet_address
        
        # Get network-aware addresses
        self.chain_addresses = get_chain_addresses('bsc')
        self.routers = self.chain_addresses.get('routers', {})
        self.flash_loan_providers = self.chain_addresses.get('flash_loan_providers', {})
        
        # ABI fetcher for dynamic contract interaction
        self.abi_fetcher = ABIFetcher()
        
        # Contract management
        self.arbitrage_executor = None
        self.contract_address = None
        
        # MEV Protection for BSC (chain_id = 56)
        self.mev_protection = UniversalMEVProtection(
            chain_id=56,
            w3=self.w3,
            private_key=config.PRIVATE_KEY
        )
        
        # Deployment info file
        self.deployment_file_path = os.path.join(
            os.path.dirname(__file__), 'deployed_contracts.json'
        )
    
    async def initialize(self):
        """Initialize the contract executor"""
        logger.info("Initializing BSC contract executor...")
        
        # Initialize ABI fetcher
        await self.abi_fetcher.__aenter__()
        
        # Load contract ABIs dynamically
        self.router_contracts = {}
        network_name = self.chain_addresses.get('network_name', 'mainnet')
        
        for router_name, router_address in self.routers.items():
            try:
                # Try to fetch ABI from BSCScan
                abi = await self.abi_fetcher.fetch_abi('bsc', network_name, router_address)
                
                if not abi:
                    # Use fallback ABI based on router type
                    if 'v2' in router_name or 'pancakeswap' in router_name:
                        abi = FALLBACK_ABIS.get('uniswap_v2_router', [])
                    else:
                        abi = []
                
                if abi:
                    self.router_contracts[router_name] = self.w3.eth.contract(
                        address=self.w3.to_checksum_address(router_address),
                        abi=abi
                    )
                    logger.info(f"Loaded {router_name} router contract with dynamic ABI")
                else:
                    logger.warning(f"No ABI found for {router_name} router")
                    
            except Exception as e:
                logger.error(f"Error loading {router_name} router ABI: {e}")
        
        # Load arbitrage executor ABI
        self.arbitrage_executor_abi = await self._load_abi("BSCArbitrageExecutor")
        
        # Check if arbitrage executor is deployed
        await self._load_or_deploy_arbitrage_executor()
        
        logger.info("BSC contract executor initialized")
    
    async def _load_abi(self, contract_name: str) -> Dict:
        """Load contract ABI from file"""
        try:
            abi_path = os.path.join(
                os.path.dirname(__file__), 
                'contracts', 
                'abis', 
                f'{contract_name}.json'
            )
            
            with open(abi_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading ABI for {contract_name}: {e}")
            raise
    
    async def _load_bytecode(self, contract_name: str) -> str:
        """Load contract bytecode from file"""
        try:
            bytecode_path = os.path.join(
                os.path.dirname(__file__), 
                'contracts', 
                'bytecode', 
                f'{contract_name}.bin'
            )
            
            with open(bytecode_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading bytecode for {contract_name}: {e}")
            raise
    
    async def _load_or_deploy_arbitrage_executor(self):
        """Load existing arbitrage executor or deploy a new one"""
        try:
            # Try to load from deployment file
            if os.path.exists(self.deployment_file_path):
                with open(self.deployment_file_path, 'r') as f:
                    deployment_data = json.load(f)
                    
                if "bsc_arbitrage_executor" in deployment_data:
                    address = deployment_data["bsc_arbitrage_executor"]
                    logger.info(f"Loading BSCArbitrageExecutor from {address}")
                    
                    self.arbitrage_executor = self.w3.eth.contract(
                        address=self.w3.to_checksum_address(address),
                        abi=self.arbitrage_executor_abi
                    )
                    self.contract_address = address
                    return
            
            # If not found, deploy a new one
            logger.info("Deploying new BSCArbitrageExecutor contract...")
            await self._deploy_arbitrage_executor()
            
        except Exception as e:
            logger.error(f"Error loading/deploying BSC arbitrage executor: {e}")
            raise
    
    async def _deploy_arbitrage_executor(self):
        """Deploy a new arbitrage executor contract"""
        try:
            # Get contract bytecode
            bytecode = await self._load_bytecode("BSCArbitrageExecutor")
            
            # Create contract deployment transaction
            contract = self.w3.eth.contract(abi=self.arbitrage_executor_abi, bytecode=bytecode)
            
            # Estimate gas for deployment
            gas_estimate = await contract.constructor().estimate_gas()
            
            # Build transaction
            tx = await contract.constructor().build_transaction({
                'from': self.wallet_address,
                'gas': int(gas_estimate * 1.2),  # Add 20% buffer
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Wait for transaction receipt
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status != 1:
                raise Exception("Contract deployment failed")
            
            # Get contract address
            contract_address = receipt.contractAddress
            
            # Save deployment info
            deployment_data = {}
            if os.path.exists(self.deployment_file_path):
                with open(self.deployment_file_path, 'r') as f:
                    deployment_data = json.load(f)
            
            deployment_data["bsc_arbitrage_executor"] = contract_address
            
            with open(self.deployment_file_path, 'w') as f:
                json.dump(deployment_data, f, indent=2)
            
            # Initialize contract instance
            self.arbitrage_executor = self.w3.eth.contract(
                address=contract_address,
                abi=self.arbitrage_executor_abi
            )
            self.contract_address = contract_address
            
            logger.info(f"BSCArbitrageExecutor deployed at {contract_address}")
            
        except Exception as e:
            logger.error(f"Error deploying BSC arbitrage executor: {e}")
            raise
    
    async def execute_arbitrage(self, params):
        """Execute cross-exchange arbitrage via smart contract"""
        try:
            logger.info(f"Executing cross-exchange arbitrage with {params['amountIn']} of token {params['tokenA']}")
            
            # Build transaction
            if params.get("useFlashLoan", False):
                # Execute with flash loan
                tx = await self.arbitrage_executor.functions.executeFlashLoanArbitrage(
                    params["tokenA"],
                    params["tokenB"],
                    params["amountIn"],
                    params["buyRouter"],
                    params["sellRouter"],
                    params["buyFee"],
                    params["sellFee"],
                    params["flashLoanProvider"],
                    params["minProfit"]
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 500000,
                    'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
                })
            else:
                # Execute direct arbitrage
                tx = await self.arbitrage_executor.functions.executeDirectArbitrage(
                    params["tokenA"],
                    params["tokenB"],
                    params["amountIn"],
                    params["buyRouter"],
                    params["sellRouter"],
                    params["buyFee"],
                    params["sellFee"],
                    params["minProfit"]
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 400000,
                    'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
                })
            
            # Check if MEV protection should be used
            if params.get("useMEVProtection", True):
                # Submit via BSC MEV protection (48Club relay)
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
                    logger.info(f"BSC arbitrage bundle submitted via MEV protection: {bundle_hash}")
                    return bundle_hash
                else:
                    logger.warning("MEV protection failed, falling back to mempool")
            
            # Fallback to standard mempool submission
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"BSC arbitrage transaction sent to mempool: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing BSC arbitrage: {e}")
            raise
    
    async def execute_triangular_arbitrage(self, params):
        """Execute triangular arbitrage via smart contract"""
        try:
            logger.info(f"Executing triangular arbitrage with {params['amountIn']} of token {params['path'][0]}")
            
            # Build transaction
            if params.get("useFlashLoan", False):
                # Execute with flash loan
                tx = await self.arbitrage_executor.functions.executeTriangularArbitrage(
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"],
                    params["flashLoanProvider"]
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 600000,
                    'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
                })
            else:
                # Execute direct triangular arbitrage
                tx = await self.arbitrage_executor.functions.executeDirectTriangularArbitrage(
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"]
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 500000,
                    'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
                })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Triangular arbitrage transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing BSC triangular arbitrage: {e}")
            raise
    
    async def execute_backrun_arbitrage(self, params):
        """Execute backrun arbitrage via smart contract"""
        try:
            logger.info(f"Executing backrun arbitrage for tx {params['targetTx']}")
            
            # Build transaction
            tx = await self.arbitrage_executor.functions.executeBackrunArbitrage(
                params["path"],
                params["routers"],
                params["fees"],
                params["amountIn"],
                params["minProfitAmount"],
                params["targetTx"],
                params["maxGasPrice"]
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 600000,
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
                'maxFeePerGas': params["maxGasPrice"]
            })
            
            # Check if MEV protection should be used for backrun
            if params.get("useMEVProtection", True) and params.get("targetTx"):
                # Submit via BSC MEV protection for backrun
                current_block = await self.w3.eth.block_number
                target_block = current_block + 1
                
                signed_tx = self.account.sign_transaction(tx)
                tx_data = {
                    "raw_tx": signed_tx.rawTransaction.hex(),
                    "priority_fee": tx.get("maxPriorityFeePerGas", 2000000000),
                    "max_fee": params["maxGasPrice"]
                }
                
                bundle_hash = await self.mev_protection.submit_backrun_bundle(
                    params["targetTx"], tx_data, target_block
                )
                
                if bundle_hash:
                    logger.info(f"BSC backrun bundle submitted via MEV protection: {bundle_hash}")
                    return bundle_hash
                else:
                    logger.warning("BSC MEV protection failed, falling back to mempool")
            
            # Fallback to standard mempool submission
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"BSC backrun arbitrage transaction sent to mempool: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing BSC backrun arbitrage: {e}")
            raise
    
    async def get_arbitrage_quote(self, params):
        """Get quote for potential arbitrage"""
        try:
            result = await self.arbitrage_executor.functions.getArbitrageQuote(
                params["tokenA"],
                params["tokenB"],
                params["amountIn"],
                params["buyRouter"],
                params["sellRouter"],
                params["buyFee"],
                params["sellFee"]
            ).call()
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting BSC arbitrage quote: {e}")
            raise
    
    async def emergency_withdraw(self, token_address, amount):
        """Emergency withdraw tokens from contract"""
        try:
            tx = await self.arbitrage_executor.functions.emergencyWithdraw(
                token_address,
                amount
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 100000,
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Emergency withdraw transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing emergency withdraw: {e}")
            raise