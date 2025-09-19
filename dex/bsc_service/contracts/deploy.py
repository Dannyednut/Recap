import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import AsyncWeb3
from eth_account import Account
import os
import subprocess
from web3 import Web3

# Import shared models
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from dex.shared.models.arbitrage_models import Token

logger = logging.getLogger(__name__)

class BSCContractDeployer:
    """Contract deployment service for BSC"""
    
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
        
    async def initialize(self) -> bool:
        """Initialize the contract deployer"""
        try:
            logger.info("Initializing BSC Contract Deployer...")
            
            # Create contracts directory if it doesn't exist
            self.contracts_dir = os.path.join(os.path.dirname(__file__), "templates")
            os.makedirs(self.contracts_dir, exist_ok=True)
            
            # Load existing deployed contracts registry
            await self._load_deployed_contracts()
            
            logger.info("BSC Contract Deployer initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize BSC Contract Deployer: {e}")
            return False
    
    async def deploy_arbitrage_contract(self, contract_path: str = None) -> Dict[str, Any]:
        """Deploy arbitrage bot contract"""
        try:
            logger.info(f"Deploying BSC arbitrage contract")
            
            if contract_path and os.path.exists(contract_path):
                # Compile from Solidity source
                contract_data = await self.compile_contract(contract_path)
            else:
                # Use pre-defined contract data
                contract_data = await self._get_arbitrage_contract_data()
                
            if not contract_data:
                return {"success": False, "error": "Failed to get contract data"}
            
            return await self._deploy_contract(
                "ArbitrageBot",
                contract_data["abi"],
                contract_data["bytecode"]
            )
            
        except Exception as e:
            logger.error(f"Error deploying arbitrage contract: {e}")
            return {"success": False, "error": str(e)}
    
    async def deploy_flashloan_contract(self, contract_path: str = None) -> Dict[str, Any]:
        """Deploy flash loan contract"""
        try:
            logger.info(f"Deploying BSC flash loan contract")
            
            if contract_path and os.path.exists(contract_path):
                # Compile from Solidity source
                contract_data = await self.compile_contract(contract_path)
            else:
                # Use pre-defined contract data
                contract_data = await self._get_flashloan_contract_data()
                
            if not contract_data:
                return {"success": False, "error": "Failed to get contract data"}
            
            return await self._deploy_contract(
                "FlashLoanBot",
                contract_data["abi"],
                contract_data["bytecode"]
            )
            
        except Exception as e:
            logger.error(f"Error deploying flash loan contract: {e}")
            return {"success": False, "error": str(e)}
    
    async def _deploy_contract(self, name: str, abi: List[Dict], bytecode: str) -> Dict[str, Any]:
        """Deploy a contract to BSC"""
        try:
            # Create contract instance
            contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
            
            # Build deployment transaction
            transaction = contract.constructor().build_transaction({
                'from': self.wallet_address,
                'gas': 3000000,
                'gasPrice': Web3.to_wei(5, 'gwei'),
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.account.key)
            
            # Send transaction
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for transaction receipt
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt.status == 1:
                return {
                    "success": True,
                    "contract_address": receipt.contractAddress,
                    "tx_hash": tx_hash.hex(),
                    "gas_used": receipt.gasUsed,
                    "block_number": receipt.blockNumber
                }
            else:
                return {
                    "success": False,
                    "error": "Transaction failed",
                    "tx_hash": tx_hash.hex()
                }
                
        except Exception as e:
            logger.error(f"Error deploying contract: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_arbitrage_contract_data(self) -> Optional[Dict[str, Any]]:
        """Get arbitrage contract bytecode and ABI"""
        try:
            # Simplified arbitrage contract (in production, you'd compile from Solidity)
            arbitrage_abi = [
                {
                    "inputs": [],
                    "name": "executeArbitrage",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                },
                {
                    "inputs": [
                        {"name": "tokenA", "type": "address"},
                        {"name": "tokenB", "type": "address"},
                        {"name": "amount", "type": "uint256"}
                    ],
                    "name": "calculateProfit",
                    "outputs": [{"name": "profit", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            
            # Placeholder bytecode (in production, compile from Solidity source)
            arbitrage_bytecode = "0x608060405234801561001057600080fd5b50610150806100206000396000f3fe608060405234801561001057600080fd5b50600436106100365760003560e01c8063a9059cbb1461003b578063dd62ed3e14610057575b600080fd5b610055600480360381019061005091906100d3565b610087565b005b610071600480360381019061006c919061010f565b6100a4565b60405161007e919061015e565b60405180910390f35b60008054906101000a900473ffffffffffffffffffffffffffffffffffffffff1690565b60006020528060005260406000206000915090505481565b600080fd5b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b60006100f3826100c8565b9050919050565b610103816100e8565b811461010e57600080fd5b50565b600081359050610120816100fa565b92915050565b60008060408385031215610139576101386100c3565b5b600061014785828601610111565b925050602061015885828601610111565b9150509250929050565b6000819050919050565b61017581610162565b82525050565b6000602082019050610190600083018461016c565b9291505056fea2646970667358221220"
            
            return {
                "abi": arbitrage_abi,
                "bytecode": arbitrage_bytecode
            }
            
        except Exception as e:
            logger.error(f"Error getting arbitrage contract data: {e}")
            return None
    
    async def _get_flashloan_contract_data(self) -> Optional[Dict[str, Any]]:
        """Get flash loan contract bytecode and ABI"""
        try:
            # Simplified flash loan contract ABI
            flashloan_abi = [
                {
                    "inputs": [
                        {"name": "asset", "type": "address"},
                        {"name": "amount", "type": "uint256"}
                    ],
                    "name": "executeFlashLoan",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                },
                {
                    "inputs": [
                        {"name": "asset", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                        {"name": "premium", "type": "uint256"},
                        {"name": "initiator", "type": "address"},
                        {"name": "params", "type": "bytes"}
                    ],
                    "name": "executeOperation",
                    "outputs": [{"name": "", "type": "bool"}],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
            # Placeholder bytecode
            flashloan_bytecode = "0x608060405234801561001057600080fd5b50610200806100206000396000f3fe608060405234801561001057600080fd5b50600436106100365760003560e01c8063a9059cbb1461003b578063dd62ed3e14610057575b600080fd5b610055600480360381019061005091906100d3565b610087565b005b610071600480360381019061006c919061010f565b6100a4565b60405161007e919061015e565b60405180910390f35b60008054906101000a900473ffffffffffffffffffffffffffffffffffffffff1690565b60006020528060005260406000206000915090505481565b600080fd5b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b60006100f3826100c8565b9050919050565b610103816100e8565b811461010e57600080fd5b50565b600081359050610120816100fa565b92915050565b60008060408385031215610139576101386100c3565b5b600061014785828601610111565b925050602061015885828601610111565b9150509250929050565b6000819050919050565b61017581610162565b82525050565b6000602082019050610190600083018461016c565b9291505056fea2646970667358221220"
            
            return {
                "abi": flashloan_abi,
                "bytecode": flashloan_bytecode
            }
            
        except Exception as e:
            logger.error(f"Error getting flash loan contract data: {e}")
            return None
    
    async def _load_deployed_contracts(self):
        """Load deployed contracts registry from file"""
        try:
            registry_file = os.path.join(self.contracts_dir, "deployed_contracts.json")
            if os.path.exists(registry_file):
                with open(registry_file, 'r') as f:
                    self.deployed_contracts = json.load(f)
                logger.info(f"Loaded {len(self.deployed_contracts)} deployed contracts from registry")
            
        except Exception as e:
            logger.error(f"Error loading deployed contracts registry: {e}")
            self.deployed_contracts = {}
    
    async def _save_deployed_contracts(self):
        """Save deployed contracts registry to file"""
        try:
            registry_file = os.path.join(self.contracts_dir, "deployed_contracts.json")
            with open(registry_file, 'w') as f:
                json.dump(self.deployed_contracts, f, indent=2)
            logger.info("Saved deployed contracts registry")
            
        except Exception as e:
            logger.error(f"Error saving deployed contracts registry: {e}")
    
    async def load_deployment_info(self, file_path: str):
        """Load deployment information from file"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    self.deployed_contracts = json.load(f)
                logger.info(f"Loaded deployment info from {file_path}")
            else:
                logger.warning(f"Deployment file {file_path} not found")
        except Exception as e:
            logger.error(f"Error loading deployment info: {e}")
    
    async def get_contract(self, contract_name: str):
        """Get deployed contract instance"""
        if contract_name not in self.deployed_contracts:
            raise Exception(f"Contract {contract_name} not deployed")
            
        contract_info = self.deployed_contracts[contract_name]
        return self.w3.eth.contract(
            address=contract_info['address'],
            abi=contract_info['abi']
        )
    
    async def ensure_contract_deployed(self, contract_name: str, contract_path: str = None) -> str:
        """Ensure contract is deployed, deploy if not found"""
        try:
            # Check if contract is already deployed
            if contract_name in self.deployed_contracts:
                address = self.deployed_contracts[contract_name]['address']
                # Verify contract exists on chain
                code = await self.w3.eth.get_code(address)
                if len(code) > 0:
                    logger.info(f"Contract {contract_name} already deployed at {address}")
                    return address
                else:
                    logger.warning(f"Contract {contract_name} address has no code, redeploying")
            
            # Deploy contract
            logger.info(f"Deploying {contract_name}...")
            if contract_name == "ArbitrageBot":
                result = await self.deploy_arbitrage_contract(contract_path)
            elif contract_name == "FlashLoanBot":
                result = await self.deploy_flashloan_contract(contract_path)
            else:
                raise Exception(f"Unknown contract type: {contract_name}")
            
            if result['success']:
                return result['contract_address']
            else:
                raise Exception(f"Deployment failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error ensuring contract deployment: {e}")
            raise
    
    async def get_deployed_contracts(self) -> Dict[str, Any]:
        """Get all deployed contracts"""
        return self.deployed_contracts.copy()
    
    async def get_contract_instance(self, name: str):
        """Get Web3 contract instance for deployed contract"""
        try:
            contract_info = self.deployed_contracts.get(name)
            if not contract_info:
                return None
            
            return self.w3.eth.contract(
                address=contract_info["address"],
                abi=contract_info["abi"]
            )
            
        except Exception as e:
            logger.error(f"Error getting contract instance: {e}")
            return None
    
    async def estimate_deployment_cost(self, contract_type: str) -> Dict[str, Any]:
        """Estimate deployment cost for a contract"""
        try:
            gas_price = Web3.to_wei(self.gas_price_gwei, 'gwei')
            gas_limit = self.gas_limit_deploy
            
            # Get BNB price in USD (simplified)
            bnb_price_usd = Decimal("300")  # Placeholder
            
            gas_cost_bnb = Decimal(gas_price * gas_limit) / Decimal(10**18)
            gas_cost_usd = gas_cost_bnb * bnb_price_usd
            
            return {
                "gas_limit": gas_limit,
                "gas_price_gwei": self.gas_price_gwei,
                "cost_bnb": float(gas_cost_bnb),
                "cost_usd": float(gas_cost_usd),
                "contract_type": contract_type
            }
            
        except Exception as e:
            logger.error(f"Error estimating deployment cost: {e}")
            return {"cost_usd": 0, "error": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get deployment service statistics"""
        return {
            "total_deployed": len(self.deployed_contracts),
            "contract_types": list(set(c.get("type", "unknown") for c in self.deployed_contracts.values())),
            "contracts_dir": self.contracts_dir,
            "gas_settings": {
                "gas_price_gwei": self.gas_price_gwei,
                "gas_limit_deploy": self.gas_limit_deploy
            }
        }
