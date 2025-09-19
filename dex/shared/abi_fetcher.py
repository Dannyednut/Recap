"""
Dynamic ABI fetching from blockchain explorers
Supports Etherscan, BSCScan, PolygonScan with caching
"""
import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional
import aiohttp
from decimal import Decimal

logger = logging.getLogger(__name__)

class ABIFetcher:
    """Fetch contract ABIs from blockchain explorers"""
    
    # Explorer API endpoints
    EXPLORERS = {
        'ethereum': {
            'mainnet': 'https://api.etherscan.io/api',
            'sepolia': 'https://api-sepolia.etherscan.io/api'
        },
        'bsc': {
            'mainnet': 'https://api.bscscan.com/api',
            'testnet': 'https://api-testnet.bscscan.com/api'
        },
        'polygon': {
            'mainnet': 'https://api.polygonscan.com/api',
            'mumbai': 'https://api-testnet.polygonscan.com/api'
        }
    }
    
    # API Keys (should be set via environment variables)
    API_KEYS = {
        'ethereum': os.getenv('ETHERSCAN_API_KEY', 'YourApiKeyToken'),
        'bsc': os.getenv('BSCSCAN_API_KEY', 'YourApiKeyToken'),
        'polygon': os.getenv('POLYGONSCAN_API_KEY', 'YourApiKeyToken')
    }
    
    def __init__(self):
        self.cache_dir = os.path.join(os.path.dirname(__file__), 'abi_cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_cache_path(self, chain: str, network: str, address: str) -> str:
        """Get cache file path for contract ABI"""
        return os.path.join(self.cache_dir, f"{chain}_{network}_{address.lower()}.json")
    
    def _is_cache_valid(self, cache_path: str, max_age_hours: int = 24) -> bool:
        """Check if cached ABI is still valid"""
        if not os.path.exists(cache_path):
            return False
        
        file_age = time.time() - os.path.getmtime(cache_path)
        return file_age < (max_age_hours * 3600)
    
    async def fetch_abi(self, 
                       chain: str, 
                       network: str, 
                       address: str, 
                       use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Fetch contract ABI from blockchain explorer
        
        Args:
            chain: blockchain name (ethereum, bsc, polygon)
            network: network name (mainnet, testnet, sepolia, mumbai)
            address: contract address
            use_cache: whether to use cached ABI if available
            
        Returns:
            Contract ABI as dict or None if failed
        """
        try:
            address = address.lower()
            cache_path = self._get_cache_path(chain, network, address)
            
            # Check cache first
            if use_cache and self._is_cache_valid(cache_path):
                try:
                    with open(cache_path, 'r') as f:
                        cached_data = json.load(f)
                    logger.info(f"Using cached ABI for {chain}:{address}")
                    return cached_data['abi']
                except Exception as e:
                    logger.warning(f"Failed to load cached ABI: {e}")
            
            # Fetch from explorer
            abi = await self._fetch_from_explorer(chain, network, address)
            
            if abi:
                # Cache the result
                cache_data = {
                    'address': address,
                    'chain': chain,
                    'network': network,
                    'abi': abi,
                    'timestamp': time.time()
                }
                
                try:
                    with open(cache_path, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                    logger.info(f"Cached ABI for {chain}:{address}")
                except Exception as e:
                    logger.warning(f"Failed to cache ABI: {e}")
            
            return abi
            
        except Exception as e:
            logger.error(f"Error fetching ABI for {chain}:{address}: {e}")
            return None
    
    async def _fetch_from_explorer(self, chain: str, network: str, address: str) -> Optional[Dict[str, Any]]:
        """Fetch ABI from blockchain explorer API"""
        try:
            if chain not in self.EXPLORERS:
                logger.error(f"Unsupported chain: {chain}")
                return None
            
            if network not in self.EXPLORERS[chain]:
                logger.error(f"Unsupported network {network} for chain {chain}")
                return None
            
            base_url = self.EXPLORERS[chain][network]
            api_key = self.API_KEYS[chain]
            
            params = {
                'module': 'contract',
                'action': 'getabi',
                'address': address,
                'apikey': api_key
            }
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(base_url, params=params) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status} fetching ABI for {address}")
                    return None
                
                data = await response.json()
                
                if data.get('status') != '1':
                    logger.error(f"API error fetching ABI: {data.get('message', 'Unknown error')}")
                    return None
                
                abi_json = data.get('result')
                if not abi_json:
                    logger.error(f"No ABI found for {address}")
                    return None
                
                # Parse ABI JSON
                try:
                    abi = json.loads(abi_json)
                    logger.info(f"Successfully fetched ABI for {chain}:{address}")
                    return abi
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid ABI JSON for {address}: {e}")
                    return None
                
        except Exception as e:
            logger.error(f"Error fetching from {chain} explorer: {e}")
            return None
    
    async def fetch_contract_info(self, 
                                 chain: str, 
                                 network: str, 
                                 address: str) -> Optional[Dict[str, Any]]:
        """Fetch complete contract information including ABI, name, etc."""
        try:
            if chain not in self.EXPLORERS:
                return None
            
            if network not in self.EXPLORERS[chain]:
                return None
            
            base_url = self.EXPLORERS[chain][network]
            api_key = self.API_KEYS[chain]
            
            # Fetch contract source code (includes ABI, name, etc.)
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': address,
                'apikey': api_key
            }
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(base_url, params=params) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                
                if data.get('status') != '1' or not data.get('result'):
                    return None
                
                result = data['result'][0]
                
                contract_info = {
                    'address': address,
                    'name': result.get('ContractName', 'Unknown'),
                    'compiler_version': result.get('CompilerVersion', ''),
                    'optimization_used': result.get('OptimizationUsed', '0') == '1',
                    'source_code': result.get('SourceCode', ''),
                    'abi': None
                }
                
                # Parse ABI if available
                abi_json = result.get('ABI')
                if abi_json and abi_json != 'Contract source code not verified':
                    try:
                        contract_info['abi'] = json.loads(abi_json)
                    except json.JSONDecodeError:
                        pass
                
                return contract_info
                
        except Exception as e:
            logger.error(f"Error fetching contract info: {e}")
            return None
    
    async def get_token_info(self, 
                           chain: str, 
                           network: str, 
                           address: str) -> Optional[Dict[str, Any]]:
        """Get token information (name, symbol, decimals) from contract"""
        try:
            abi = await self.fetch_abi(chain, network, address)
            if not abi:
                return None
            
            # Standard ERC20 functions we need
            required_functions = ['name', 'symbol', 'decimals']
            
            # Check if ABI has required functions
            available_functions = [func['name'] for func in abi if func.get('type') == 'function']
            
            if not all(func in available_functions for func in required_functions):
                logger.warning(f"Contract {address} missing required ERC20 functions")
                return None
            
            return {
                'address': address,
                'abi': abi,
                'is_erc20': True
            }
            
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return None

# Global ABI fetcher instance
_abi_fetcher = None

async def get_abi_fetcher() -> ABIFetcher:
    """Get global ABI fetcher instance"""
    global _abi_fetcher
    if _abi_fetcher is None:
        _abi_fetcher = ABIFetcher()
        await _abi_fetcher.__aenter__()
    return _abi_fetcher

async def fetch_contract_abi(chain: str, network: str, address: str) -> Optional[Dict[str, Any]]:
    """Convenience function to fetch contract ABI"""
    async with ABIFetcher() as fetcher:
        return await fetcher.fetch_abi(chain, network, address)

# Common contract ABIs that can be used as fallbacks
FALLBACK_ABIS = {
    'erc20': [
        {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
        {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
    ],
    'uniswap_v2_pair': [
        {"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"}
    ],
    'uniswap_v2_factory': [
        {"constant": True, "inputs": [{"name": "", "type": "address"}, {"name": "", "type": "address"}], "name": "getPair", "outputs": [{"name": "", "type": "address"}], "type": "function"}
    ]
}
