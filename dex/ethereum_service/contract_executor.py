"""
Smart contract execution interface for Ethereum arbitrage
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

from .flashbots_relay import FlashbotsIntegration
from .config import EthereumConfig

logger = logging.getLogger(__name__)

class ContractExecutor:
    """Execute arbitrage opportunities using smart contracts"""
    
    # Router addresses
    ROUTERS = {
        'uniswap_v2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
        'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
        'sushiswap_v2': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'
    }
    
    # Flash loan providers
    FLASH_LOAN_PROVIDERS = {
        'aave': '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2',
        'balancer': '0xBA12222222228d8Ba445958a75a0704d566BF2C8'
    }
    
    def __init__(self, engine, config):
        """Initialize contract executor with engine and config"""
        self.engine = engine
        self.config = config
        
        # Account setup
        self.account: LocalAccount = Account.from_key(config.PRIVATE_KEY)
        self.wallet_address = self.account.address
        
        # Contract management
        self.deployer = ContractDeployer(engine.w3, config.PRIVATE_KEY)
        self.arbitrage_contract = None
        self.contract_address = None
        
        # Flashbots integration
        self.flashbots = FlashbotsIntegration(
            engine.w3, 
            config.PRIVATE_KEY,
            config.FLASHBOTS_RELAY_URL if hasattr(config, 'FLASHBOTS_RELAY_URL') else None
        )
        
        # Deployment info file
        self.deployment_file = os.path.join(
            os.path.dirname(__file__), 'deployed_contracts.json'
        )
    
    async def initialize(self):
        """Initialize the contract executor"""
        logger.info("Initializing Ethereum contract executor...")
        
        # Load contract ABIs
        self.uniswap_v2_router_abi = await self.engine.load_abi("UniswapV2Router")
        self.uniswap_v3_router_abi = await self.engine.load_abi("UniswapV3Router")
        self.sushiswap_router_abi = await self.engine.load_abi("SushiSwapRouter")
        self.arbitrage_executor_abi = await self.engine.load_abi("ArbitrageExecutor")
        
        # Initialize router contracts
        self.uniswap_v2_router = self.engine.w3.eth.contract(
            address=self.engine.w3.to_checksum_address(self.router_addresses["uniswap_v2"]),
            abi=self.uniswap_v2_router_abi
        )
        
        self.uniswap_v3_router = self.engine.w3.eth.contract(
            address=self.engine.w3.to_checksum_address(self.router_addresses["uniswap_v3"]),
            abi=self.uniswap_v3_router_abi
        )
        
        self.sushiswap_router = self.engine.w3.eth.contract(
            address=self.engine.w3.to_checksum_address(self.router_addresses["sushiswap"]),
            abi=self.sushiswap_router_abi
        )
        
        # Check if arbitrage executor is deployed
        await self._load_or_deploy_arbitrage_executor()
    
    async def _load_or_deploy_arbitrage_executor(self):
        """Load existing arbitrage executor or deploy a new one"""
        try:
            # Try to load from deployment file
            if os.path.exists(self.deployment_file_path):
                with open(self.deployment_file_path, 'r') as f:
                    deployment_data = json.load(f)
                    
                if "arbitrage_executor" in deployment_data:
                    address = deployment_data["arbitrage_executor"]
                    logger.info(f"Loading ArbitrageExecutor from {address}")
                    
                    self.arbitrage_executor = self.engine.w3.eth.contract(
                        address=self.engine.w3.to_checksum_address(address),
                        abi=self.arbitrage_executor_abi
                    )
                    return
            
            # If not found, deploy a new one
            logger.info("Deploying new ArbitrageExecutor contract...")
            await self._deploy_arbitrage_executor()
            
        except Exception as e:
            logger.error(f"Error loading/deploying arbitrage executor: {e}")
            raise
    
    async def _deploy_arbitrage_executor(self):
        """Deploy a new arbitrage executor contract"""
        try:
            # Get contract bytecode
            bytecode = await self.engine.load_bytecode("ArbitrageExecutor")
            
            # Create contract deployment transaction
            contract = self.engine.w3.eth.contract(abi=self.arbitrage_executor_abi, bytecode=bytecode)
            
            # Estimate gas for deployment
            constructor_args = [
                self.router_addresses["uniswap_v2"],
                self.router_addresses["uniswap_v3"],
                self.router_addresses["sushiswap"],
                self.flash_loan_providers["aave"],
                self.flash_loan_providers["balancer"]
            ]
            
            gas_estimate = await contract.constructor(*constructor_args).estimate_gas()
            
            # Build transaction
            tx = await contract.constructor(*constructor_args).build_transaction({
                'from': self.account.address,
                'gas': int(gas_estimate * 1.2),  # Add 20% buffer
                'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address)
            })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.engine.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Wait for transaction receipt
            receipt = await self.engine.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status != 1:
                raise Exception("Contract deployment failed")
            
            # Get contract address
            contract_address = receipt.contractAddress
            
            # Save deployment info
            deployment_data = {}
            if os.path.exists(self.deployment_file_path):
                with open(self.deployment_file_path, 'r') as f:
                    deployment_data = json.load(f)
            
            deployment_data["arbitrage_executor"] = contract_address
            
            with open(self.deployment_file_path, 'w') as f:
                json.dump(deployment_data, f, indent=2)
            
            # Initialize contract instance
            self.arbitrage_executor = self.engine.w3.eth.contract(
                address=contract_address,
                abi=self.arbitrage_executor_abi
            )
            
            logger.info(f"ArbitrageExecutor deployed at {contract_address}")
            
        except Exception as e:
            logger.error(f"Error deploying arbitrage executor: {e}")
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
                    'from': self.account.address,
                    'gas': 500000,
                    'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address)
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
                    'from': self.account.address,
                    'gas': 400000,
                    'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address)
                })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.engine.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Arbitrage transaction sent: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            raise
    
    async def execute_triangular_arbitrage(self, params):
        """Execute triangular arbitrage via smart contract"""
        try:
            logger.info(f"Executing triangular arbitrage with {params['amountIn']} of token {params['path'][0]}")
            
            # Build transaction
            if params.get("flashLoanProvider", 0) > 0:
                # Execute with flash loan
                tx = await self.arbitrage_executor.functions.executeTriangularArbitrage(
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"],
                    params["flashLoanProvider"]
                ).build_transaction({
                    'from': self.account.address,
                    'gas': 600000,
                    'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address)
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
                    'from': self.account.address,
                    'gas': 500000,
                    'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address)
                })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.engine.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Triangular arbitrage transaction sent: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error executing triangular arbitrage: {e}")
            raise
    
    async def execute_backrun_arbitrage(self, params):
        """Execute backrun arbitrage via smart contract"""
        try:
            logger.info(f"Executing backrun arbitrage targeting tx {params['targetTxHash']}")
            
            # Build transaction
            if params.get("flashLoanProvider", 0) > 0:
                # Execute with flash loan
                tx = await self.arbitrage_executor.functions.executeBackrunArbitrage(
                    params["targetTxHash"],
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"],
                    params["flashLoanProvider"],
                    params["maxGasPrice"]
                ).build_transaction({
                    'from': self.account.address,
                    'gas': 700000,
                    'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address),
                    'maxFeePerGas': params["maxGasPrice"]
                })
            else:
                # Execute direct backrun arbitrage
                tx = await self.arbitrage_executor.functions.executeDirectBackrunArbitrage(
                    params["targetTxHash"],
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"],
                    params["minProfitAmount"],
                    params["maxGasPrice"]
                ).build_transaction({
                    'from': self.account.address,
                    'gas': 600000,
                    'nonce': await self.engine.w3.eth.get_transaction_count(self.account.address),
                    'maxFeePerGas': params["maxGasPrice"]
                })
            
            # Check if Flashbots should be used for backrun
            if params.get("useFlashbots", True) and params.get("targetTxHash"):
                # Submit via Flashbots bundle for MEV protection
                bundle_hash = await self.flashbots.submit_backrun_arbitrage(
                    params["targetTxHash"],
                    params,
                    self
                )
                
                if bundle_hash:
                    logger.info(f"Backrun bundle submitted via Flashbots: {bundle_hash}")
                    return bundle_hash
                else:
                    logger.warning("Flashbots submission failed, falling back to mempool")
            
            # Fallback to standard mempool submission
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.engine.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Backrun arbitrage transaction sent to mempool: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error executing backrun arbitrage: {e}")
            raise
    
    async def get_profit_from_receipt(self, receipt):
        """Extract profit from transaction receipt by parsing events"""
        try:
            # Get ArbitrageExecuted event
            arbitrage_event = self.arbitrage_executor.events.ArbitrageExecuted().process_receipt(receipt)
            
            if arbitrage_event:
                return arbitrage_event[0].args.profit
            
            # Try TriangularArbitrageExecuted event
            triangular_event = self.arbitrage_executor.events.TriangularArbitrageExecuted().process_receipt(receipt)
            
            if triangular_event:
                return triangular_event[0].args.profit
            
            # Try BackrunArbitrageExecuted event
            backrun_event = self.arbitrage_executor.events.BackrunArbitrageExecuted().process_receipt(receipt)
            
            if backrun_event:
                return backrun_event[0].args.profit
            
            # No profit event found
            return 0
            
        except Exception as e:
            logger.error(f"Error extracting profit from receipt: {e}")
            return 0
    
    async def get_arbitrage_quote(self, params):
        """Get quote for arbitrage opportunity"""
        try:
            if "tokenB" in params:  # Cross-exchange arbitrage
                result = await self.arbitrage_executor.functions.getArbitrageQuote(
                    params["tokenA"],
                    params["tokenB"],
                    params["amountIn"],
                    params["buyRouter"],
                    params["sellRouter"],
                    params["buyFee"],
                    params["sellFee"]
                ).call()
                
                return {
                    "expectedProfit": result[0],
                    "tokenBAmount": result[1],
                    "tokenAAmount": result[2]
                }
            elif "path" in params:  # Triangular arbitrage
                result = await self.arbitrage_executor.functions.getTriangularArbitrageQuote(
                    params["path"],
                    params["routers"],
                    params["fees"],
                    params["amountIn"]
                ).call()
                
                return {
                    "expectedProfit": result[0],
                    "intermediateAmounts": result[1]
                }
            else:
                raise ValueError("Invalid quote parameters")
                
        except Exception as e:
            logger.error(f"Error getting arbitrage quote: {e}")
            return {
                "expectedProfit": 0,
                "error": str(e)
            }