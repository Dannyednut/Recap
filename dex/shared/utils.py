"""
Shared utility functions for ArbitrageWise system
"""
import json
import os
from typing import Dict, Any, Optional, List
from decimal import Decimal
import asyncio
from functools import wraps

def load_contract_abi(contract_name: str, abi_dir: str = None) -> Dict[str, Any]:
    """
    Load contract ABI from JSON file
    
    Args:
        contract_name: Name of the contract (without .json extension)
        abi_dir: Directory containing ABI files (optional)
    
    Returns:
        Contract ABI as dictionary
    """
    if abi_dir is None:
        # Default to contracts directory relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        abi_dir = os.path.join(current_dir, "..", "..", "contracts", "abis")
    
    abi_file = os.path.join(abi_dir, f"{contract_name}.json")
    
    try:
        with open(abi_file, 'r') as f:
            abi_data = json.load(f)
        
        # Handle different ABI file formats
        if isinstance(abi_data, dict):
            # Truffle/Hardhat format
            if 'abi' in abi_data:
                return abi_data['abi']
            # Direct ABI format
            return abi_data
        elif isinstance(abi_data, list):
            # Direct ABI array format
            return abi_data
        else:
            raise ValueError(f"Invalid ABI format in {abi_file}")
            
    except FileNotFoundError:
        # Return minimal ABI for common ERC20 functions if file not found
        if contract_name.lower() in ['erc20', 'token']:
            return get_erc20_abi()
        raise FileNotFoundError(f"ABI file not found: {abi_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in ABI file {abi_file}: {e}")

def get_erc20_abi() -> List[Dict[str, Any]]:
    """
    Get standard ERC20 ABI for token contracts
    
    Returns:
        ERC20 ABI as list of function definitions
    """
    return [
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_to", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_from", "type": "address"},
                {"name": "_to", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "transferFrom",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [
                {"name": "_owner", "type": "address"},
                {"name": "_spender", "type": "address"}
            ],
            "name": "allowance",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        }
    ]

def wei_to_ether(wei_amount: int) -> Decimal:
    """
    Convert wei to ether
    
    Args:
        wei_amount: Amount in wei
    
    Returns:
        Amount in ether as Decimal
    """
    return Decimal(wei_amount) / Decimal(10**18)

def ether_to_wei(ether_amount: Decimal) -> int:
    """
    Convert ether to wei
    
    Args:
        ether_amount: Amount in ether
    
    Returns:
        Amount in wei as integer
    """
    return int(ether_amount * Decimal(10**18))

def format_token_amount(amount: int, decimals: int) -> Decimal:
    """
    Format token amount from raw integer to decimal representation
    
    Args:
        amount: Raw token amount
        decimals: Token decimal places
    
    Returns:
        Formatted amount as Decimal
    """
    return Decimal(amount) / Decimal(10**decimals)

def to_raw_token_amount(amount: Decimal, decimals: int) -> int:
    """
    Convert decimal token amount to raw integer representation
    
    Args:
        amount: Decimal token amount
        decimals: Token decimal places
    
    Returns:
        Raw token amount as integer
    """
    return int(amount * Decimal(10**decimals))

def retry_async(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for retrying async functions with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator

def calculate_slippage_amount(amount: Decimal, slippage_percent: Decimal) -> Decimal:
    """
    Calculate minimum amount after slippage
    
    Args:
        amount: Original amount
        slippage_percent: Slippage percentage (e.g., 0.5 for 0.5%)
    
    Returns:
        Minimum amount after slippage
    """
    slippage_multiplier = Decimal("1") - (slippage_percent / Decimal("100"))
    return amount * slippage_multiplier

def validate_address(address: str) -> bool:
    """
    Basic validation for Ethereum-style addresses
    
    Args:
        address: Address to validate
    
    Returns:
        True if address format is valid
    """
    if not address or not isinstance(address, str):
        return False
    
    # Remove 0x prefix if present
    if address.startswith('0x'):
        address = address[2:]
    
    # Check if it's 40 hex characters
    if len(address) != 40:
        return False
    
    try:
        int(address, 16)
        return True
    except ValueError:
        return False

def safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """
    Safely convert value to Decimal with fallback
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Decimal representation of value or default
    """
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (ValueError, TypeError, decimal.InvalidOperation):
        return default
