"""
Deployment script for Ethereum arbitrage smart contracts
"""
import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import AsyncWeb3
from eth_account import Account
import os
import subprocess

logger = logging.getLogger(__name__)

class ContractDeployer:
    """Deploy and manage arbitrage smart contracts"""
    
    def __init__(self, w3: AsyncWeb3, private_key: str):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.wallet_address = self.account.address
        self.deployed_contracts = {}
        
    async def compile_contract(self, contract_path: str) -> Dict[str, Any]:
        """Compile Solidity contract using solc"""
        try:
            # Use solc to compile the contract
            result = subprocess.run([
                'solc',
                '--combined-json', 'abi,bin',
                '--optimize',
                contract_path
            ], capture_output=True, text=True, cwd=os.path.dirname(contract_path))
            
            if result.returncode != 0:
                logger.error(f"Compilation failed: {result.stderr}")
                raise Exception(f"Contract compilation failed: {result.stderr}")
            
            compiled = json.loads(result.stdout)
            contract_name = os.path.basename(contract_path).replace('.sol', '')
            
            # Extract ABI and bytecode
            contract_key = f"{contract_path}:{contract_name}"
            if contract_key not in compiled['contracts']:
                # Try without path prefix
                contract_key = f":{contract_name}"
                
            if contract_key not in compiled['contracts']:
                raise Exception(f"Contract {contract_name} not found in compilation output")
                
            contract_data = compiled['contracts'][contract_key]
            
            return {
                'abi': json.loads(contract_data['abi']),
                'bytecode': contract_data['bin']
            }
            
        except FileNotFoundError:
            logger.error("solc compiler not found. Please install Solidity compiler.")
            raise Exception("Solidity compiler not installed")
        except Exception as e:
            logger.error(f"Error compiling contract: {e}")
            raise
    
    async def deploy_contract(self, contract_name: str, abi: list, bytecode: str, constructor_args: list = None) -> str:
        """Deploy a smart contract"""
        try:
            # Create contract instance
            contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
            
            # Build constructor transaction
            if constructor_args:
                constructor = contract.constructor(*constructor_args)
            else:
                constructor = contract.constructor()
            
            # Get gas estimate
            gas_estimate = await constructor.estimate_gas({'from': self.wallet_address})
            gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
            
            # Get gas price
            gas_price = await self.w3.eth.gas_price
            
            # Build transaction
            transaction = await constructor.build_transaction({
                'from': self.wallet_address,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
            })
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(transaction)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for confirmation
            logger.info(f"Deploying {contract_name}, tx hash: {tx_hash.hex()}")
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                contract_address = receipt.contractAddress
                logger.info(f"{contract_name} deployed successfully at {contract_address}")
                
                # Store deployed contract info
                self.deployed_contracts[contract_name] = {
                    'address': contract_address,
                    'abi': abi,
                    'bytecode': bytecode,
                    'tx_hash': tx_hash.hex()
                }
                
                return contract_address
            else:
                raise Exception(f"Contract deployment failed: {receipt}")
                
        except Exception as e:
            logger.error(f"Error deploying {contract_name}: {e}")
            raise
    
    async def get_contract(self, contract_name: str):
        """Get deployed contract instance"""
        if contract_name not in self.deployed_contracts:
            raise Exception(f"Contract {contract_name} not deployed")
            
        contract_info = self.deployed_contracts[contract_name]
        return self.w3.eth.contract(
            address=contract_info['address'],
            abi=contract_info['abi']
        )
    
    async def deploy_arbitrage_executor(self) -> str:
        """Deploy the ArbitrageExecutor contract"""
        try:
            contract_path = os.path.join(os.path.dirname(__file__), 'ArbitrageExecutor.sol')
            
            # Compile contract
            compiled = await self.compile_contract(contract_path)
            
            # Deploy contract
            address = await self.deploy_contract(
                'ArbitrageExecutor',
                compiled['abi'],
                compiled['bytecode']
            )
            
            return address
            
        except Exception as e:
            logger.error(f"Error deploying ArbitrageExecutor: {e}")
            raise
    
    def save_deployment_info(self, file_path: str):
        """Save deployment information to file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(self.deployed_contracts, f, indent=2)
            logger.info(f"Deployment info saved to {file_path}")
        except Exception as e:
            logger.error(f"Error saving deployment info: {e}")
    
    def load_deployment_info(self, file_path: str):
        """Load deployment information from file"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    self.deployed_contracts = json.load(f)
                logger.info(f"Deployment info loaded from {file_path}")
            else:
                logger.warning(f"Deployment file {file_path} not found")
        except Exception as e:
            logger.error(f"Error loading deployment info: {e}")

class ArbitrageContractInterface:
    """Interface for interacting with deployed arbitrage contracts"""
    
    def __init__(self, w3: AsyncWeb3, contract_address: str, abi: list, private_key: str):
        self.w3 = w3
        self.contract = w3.eth.contract(address=contract_address, abi=abi)
        self.account = Account.from_key(private_key)
        self.wallet_address = self.account.address
    
    async def execute_arbitrage(self, params: Dict[str, Any]) -> str:
        """Execute arbitrage through smart contract"""
        try:
            # Build transaction
            function = self.contract.functions.executeArbitrage(params)
            
            # Estimate gas
            gas_estimate = await function.estimate_gas({'from': self.wallet_address})
            gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
            
            # Get gas price
            gas_price = await self.w3.eth.gas_price
            
            # Build transaction
            transaction = await function.build_transaction({
                'from': self.wallet_address,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
            })
            
            # Sign and send
            signed_txn = self.account.sign_transaction(transaction)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"Arbitrage execution tx: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            raise
    
    async def get_arbitrage_quote(self, params: Dict[str, Any]) -> int:
        """Get quote for potential arbitrage profit"""
        try:
            result = await self.contract.functions.getArbitrageQuote(
                params['tokenA'],
                params['tokenB'],
                params['amountIn'],
                params['buyRouter'],
                params['sellRouter'],
                params['buyFee'],
                params['sellFee']
            ).call()
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting arbitrage quote: {e}")
            return 0
    
    async def emergency_withdraw(self, token_address: str, amount: int) -> str:
        """Emergency withdraw tokens from contract"""
        try:
            function = self.contract.functions.emergencyWithdraw(token_address, amount)
            
            # Build and send transaction
            transaction = await function.build_transaction({
                'from': self.wallet_address,
                'gas': 100000,
                'gasPrice': await self.w3.eth.gas_price,
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
            })
            
            signed_txn = self.account.sign_transaction(transaction)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error in emergency withdraw: {e}")
            raise