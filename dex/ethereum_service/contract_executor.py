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
from .engine import EthereumEngine
from ..shared.contract_addresses import get_chain_addresses, get_router_address
from ..shared.abi_fetcher import ABIFetcher, FALLBACK_ABIS

logger = logging.getLogger(__name__)

class ContractExecutor:
    """Execute arbitrage opportunities using smart contracts"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        self.w3 = engine.w3
        self.account = engine.account
        self.wallet_address = engine.wallet_address
        
        # Get network-aware addresses
        self.chain_addresses = get_chain_addresses('ethereum')
        self.routers = self.chain_addresses.get('routers', {})
        self.flash_loan_providers = self.chain_addresses.get('flash_loan_providers', {})
        
        # ABI fetcher for dynamic contract interaction
        self.abi_fetcher = ABIFetcher()
        
        # Contract management
        self.arbitrage_executor = None
        self.contract_address = None
        
        # Initialize router addresses from network config
        self.router_addresses = self.routers
        
        # Flashbots integration
        self.flashbots = FlashbotsIntegration(
            engine.w3, 
            config.PRIVATE_KEY,
            config.FLASHBOTS_RELAY_URL if hasattr(config, 'FLASHBOTS_RELAY_URL') else None
        )
        
        # Deployment info file
        self.deployment_file_path = os.path.join(
            os.path.dirname(__file__), 'deployed_contracts.json'
        )
    
    async def initialize(self):
        """Initialize the contract executor"""
        logger.info("Initializing Ethereum contract executor...")
        
        # Initialize ABI fetcher
        await self.abi_fetcher.__aenter__()
        
        # Load contract ABIs dynamically
        self.router_contracts = {}
        network_name = self.chain_addresses.get('network_name', 'mainnet')
        
        for router_name, router_address in self.routers.items():
            try:
                # Try to fetch ABI from Etherscan
                abi = await self.abi_fetcher.fetch_abi('ethereum', network_name, router_address)
                
                if not abi:
                    # Use fallback ABI based on router type
                    if 'v2' in router_name or 'uniswap_v2' in router_name:
                        abi = FALLBACK_ABIS.get('uniswap_v2_router', [])
                    elif 'v3' in router_name or 'uniswap_v3' in router_name:
                        abi = FALLBACK_ABIS.get('uniswap_v3_router', [])
                    elif 'sushiswap' in router_name:
                        abi = FALLBACK_ABIS.get('uniswap_v2_router', [])  # SushiSwap uses V2 interface
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
        from ..shared.utils import load_contract_abi
        self.arbitrage_executor_abi = load_contract_abi("EthereumArbitrageExecutor")
        
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
                self.router_addresses.get("uniswap_v2", "0x0000000000000000000000000000000000000000"),
                self.router_addresses.get("uniswap_v3", "0x0000000000000000000000000000000000000000"),
                self.router_addresses.get("sushiswap", "0x0000000000000000000000000000000000000000"),
                self.flash_loan_providers.get("aave", "0x0000000000000000000000000000000000000000"),
                self.flash_loan_providers.get("balancer", "0x0000000000000000000000000000000000000000")
            ]
            
            gas_estimate = await contract.constructor(*constructor_args).estimate_gas()
            
            # Build transaction
            tx = await contract.constructor(*constructor_args).build_transaction({
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
            
            deployment_data["arbitrage_executor"] = contract_address
            
            with open(self.deployment_file_path, 'w') as f:
                json.dump(deployment_data, f, indent=2)
            
            # Initialize contract instance
            self.arbitrage_executor = self.w3.eth.contract(
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
    
        """Get quote for arbitrage opportunity"""
        try:
            if "tokenB" in params:  # Cross-exchange arbitrage
                result = await self.arbitrage_executor.functions.getArbitrageQuote(
                    params["tokenA"],
                    params["tokenB"],
                    params["amountIn"],
                    self.router_contracts[params["buyRouter"]].address,
                    self.router_contracts[params["sellRouter"]].address,
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
                    [self.router_contracts[router].address for router in params["routers"]],
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