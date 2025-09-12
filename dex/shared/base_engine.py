from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseEngine(ABC):
    """Base class for blockchain engine implementations"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the engine with necessary connections and configurations"""
        pass
    
    @abstractmethod
    def get_web3_instance(self):
        """Get the web3 instance or equivalent for the blockchain"""
        pass
    
    @abstractmethod
    def get_account(self):
        """Get the account used for transactions"""
        pass
    
    @abstractmethod
    def get_contract(self, address: str, abi: List[Dict[str, Any]]):
        """Get a contract instance at the specified address"""
        pass
    
    @abstractmethod
    def get_token_balance(self, token_address: str, account_address: str) -> int:
        """Get token balance for an account"""
        pass
    
    @abstractmethod
    def get_native_balance(self, account_address: str) -> int:
        """Get native token (ETH, BNB, etc.) balance for an account"""
        pass
    
    @abstractmethod
    def get_gas_price(self) -> int:
        """Get current gas price"""
        pass
    
    @abstractmethod
    def estimate_gas(self, tx: Dict[str, Any]) -> int:
        """Estimate gas for a transaction"""
        pass
    
    @abstractmethod
    def send_transaction(self, tx: Dict[str, Any]) -> str:
        """Send a transaction and return the transaction hash"""
        pass
    
    @abstractmethod
    def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        """Wait for a transaction receipt"""
        pass
    
    @abstractmethod
    def get_block(self, block_identifier: Any) -> Dict[str, Any]:
        """Get block information"""
        pass
    
    @abstractmethod
    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction information"""
        pass
    
    @abstractmethod
    def get_transaction_count(self, address: str) -> int:
        """Get transaction count (nonce) for an address"""
        pass
    
    @abstractmethod
    def get_chain_id(self) -> int:
        """Get the chain ID"""
        pass
    
    @abstractmethod
    def get_network_name(self) -> str:
        """Get the network name"""
        pass
    
    @abstractmethod
    def is_contract(self, address: str) -> bool:
        """Check if an address is a contract"""
        pass
    
    @abstractmethod
    def get_logs(self, filter_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get logs matching the filter parameters"""
        pass
    
    @abstractmethod
    def call_function(self, contract, function_name: str, *args, **kwargs) -> Any:
        """Call a contract function"""
        pass
    
    @abstractmethod
    def deploy_contract(self, abi: List[Dict[str, Any]], bytecode: str, *args) -> str:
        """Deploy a contract and return its address"""
        pass