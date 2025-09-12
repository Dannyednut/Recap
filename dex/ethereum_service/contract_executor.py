"""
Smart contract execution interface for Ethereum arbitrage
"""
import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from web3 import AsyncWeb3
from eth_account import Account
import os

from .contracts.deploy import ContractDeployer, ArbitrageContractInterface
from .config import EthereumConfig

logger = logging.getLogger(__name__)

class EthereumContractExecutor:
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
    
    def __init__(self, w3: AsyncWeb3, config: EthereumConfig):
        self.w3 = w3
        self.config = config
        self.account = Account.from_key(config.PRIVATE_KEY)
        self.wallet_address = self.account.address
        
        # Contract management
        self.deployer = ContractDeployer(w3, config.PRIVATE_KEY)
        self.arbitrage_contract = None
        self.contract_address = None
        
        # Deployment info file
        self.deployment_file = os.path.join(
            os.path.dirname(__file__), 'deployed_contracts.json'
        )
    
    async def initialize(self):
        """Initialize contract executor"""
        try:
            logger.info("Initializing contract executor...")
            
            # Load existing deployment info
            self.deployer.load_deployment_info(self.deployment_file)
            
            # Check if contract is already deployed
            if 'ArbitrageExecutor' in self.deployer.deployed_contracts:
                contract_info = self.deployer.deployed_contracts['ArbitrageExecutor']
                self.contract_address = contract_info['address']
                
                # Verify contract exists on chain
                code = await self.w3.eth.get_code(self.contract_address)
                if code and code != b'':
                    self.arbitrage_contract = ArbitrageContractInterface(
                        self.w3,
                        self.contract_address,
                        contract_info['abi'],
                        self.config.PRIVATE_KEY
                    )
                    logger.info(f"Using existing contract at {self.contract_address}")
                    return
                else:
                    logger.warning("Contract address has no code, redeploying...")
            
            # Try to deploy new contract
            try:
                await self._deploy_contracts()
            except Exception as deploy_error:
                logger.warning(f"Contract deployment failed: {deploy_error}")
                logger.info("Contract executor will run in monitoring-only mode (no execution)")
                # Continue without contracts for price monitoring
            
        except Exception as e:
            logger.warning(f"Contract executor initialization failed: {e}")
            logger.info("Continuing without contract deployment - price monitoring will still work")
    
    async def _deploy_contracts(self):
        """Deploy arbitrage contracts"""
        try:
            logger.info("Deploying arbitrage contracts...")
            
            # Deploy ArbitrageExecutor
            self.contract_address = await self.deployer.deploy_arbitrage_executor()
            
            # Create interface
            contract_info = self.deployer.deployed_contracts['ArbitrageExecutor']
            self.arbitrage_contract = ArbitrageContractInterface(
                self.w3,
                self.contract_address,
                contract_info['abi'],
                self.config.PRIVATE_KEY
            )
            
            # Save deployment info
            self.deployer.save_deployment_info(self.deployment_file)
            
            logger.info("Contracts deployed successfully")
            
        except Exception as e:
            logger.error(f"Error deploying contracts: {e}")
            raise
    
    async def execute_cross_arbitrage(
        self,
        token_a: str,
        token_b: str,
        amount_in: int,
        buy_dex: str,
        sell_dex: str,
        buy_fee: int = 3000,  # 0.3% for V3
        sell_fee: int = 3000,
        use_flash_loan: bool = True,
        flash_provider: str = 'balancer'
    ) -> Optional[str]:
        """Execute cross-DEX arbitrage"""
        try:
            if not self.arbitrage_contract:
                raise Exception("Contract not initialized")
            
            # Prepare arbitrage parameters
            params = {
                'tokenA': token_a,
                'tokenB': token_b,
                'amountIn': amount_in,
                'buyRouter': self.ROUTERS[buy_dex],
                'sellRouter': self.ROUTERS[sell_dex],
                'buyFee': buy_fee,
                'sellFee': sell_fee,
                'useFlashLoan': use_flash_loan,
                'flashLoanProvider': self.FLASH_LOAN_PROVIDERS.get(flash_provider, self.FLASH_LOAN_PROVIDERS['balancer']),
                'minProfit': 0  # Will be calculated
            }
            
            # Get quote first to verify profitability
            expected_profit = await self.arbitrage_contract.get_arbitrage_quote(params)
            
            if expected_profit <= 0:
                logger.warning("Arbitrage not profitable according to quote")
                return None
            
            logger.info(f"Expected profit: {expected_profit} wei")
            
            # Execute arbitrage
            tx_hash = await self.arbitrage_contract.execute_arbitrage(params)
            
            logger.info(f"Arbitrage executed, tx: {tx_hash}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error executing cross arbitrage: {e}")
            return None
    
    async def get_arbitrage_quote(
        self,
        token_a: str,
        token_b: str,
        amount_in: int,
        buy_dex: str,
        sell_dex: str,
        buy_fee: int = 3000,
        sell_fee: int = 3000
    ) -> int:
        """Get arbitrage profit quote"""
        try:
            if not self.arbitrage_contract:
                return 0
            
            params = {
                'tokenA': token_a,
                'tokenB': token_b,
                'amountIn': amount_in,
                'buyRouter': self.ROUTERS[buy_dex],
                'sellRouter': self.ROUTERS[sell_dex],
                'buyFee': buy_fee,
                'sellFee': sell_fee
            }
            
            return await self.arbitrage_contract.get_arbitrage_quote(params)
            
        except Exception as e:
            logger.error(f"Error getting quote: {e}")
            return 0
    
    async def fund_contract(self, token_address: str, amount: int):
        """Fund the arbitrage contract with tokens"""
        try:
            # For ETH
            if token_address.lower() == "0x0" or token_address.upper() == "ETH":
                tx = {
                    'to': self.contract_address,
                    'value': amount,
                    'gas': 21000,
                    'gasPrice': await self.w3.eth.gas_price,
                    'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
                }
                
                signed_txn = self.account.sign_transaction(tx)
                tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                
                logger.info(f"Funded contract with ETH, tx: {tx_hash.hex()}")
                return tx_hash.hex()
            
            # For ERC20 tokens
            else:
                # ERC20 transfer would go here
                # This is a simplified implementation
                logger.info(f"ERC20 funding not implemented for {token_address}")
                return None
                
        except Exception as e:
            logger.error(f"Error funding contract: {e}")
            return None
    
    async def withdraw_from_contract(self, token_address: str, amount: int):
        """Emergency withdraw from contract"""
        try:
            if not self.arbitrage_contract:
                raise Exception("Contract not initialized")
            
            tx_hash = await self.arbitrage_contract.emergency_withdraw(token_address, amount)
            logger.info(f"Emergency withdraw tx: {tx_hash}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error withdrawing from contract: {e}")
            return None
    
    def get_contract_address(self) -> Optional[str]:
        """Get deployed contract address"""
        return self.contract_address
    
    def is_initialized(self) -> bool:
        """Check if executor is initialized"""
        return self.arbitrage_contract is not None
    
    async def get_contract_balance(self, token_address: str = "0x0") -> int:
        """Get contract token balance"""
        try:
            if not self.contract_address:
                return 0
            
            if token_address.lower() == "0x0" or token_address.upper() == "ETH":
                # ETH balance
                balance = await self.w3.eth.get_balance(self.contract_address)
                return balance
            else:
                # ERC20 balance (simplified)
                # Would need to call balanceOf on the token contract
                return 0
                
        except Exception as e:
            logger.error(f"Error getting contract balance: {e}")
            return 0