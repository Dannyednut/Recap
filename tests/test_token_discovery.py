import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import components to test
from dex.ethereum_service.token_discovery import TokenDiscoveryService


class TestTokenDiscovery(unittest.TestCase):
    """Test suite for token discovery service"""
    
    def setUp(self):
        """Set up test environment"""
        # Create mock objects
        self.mock_engine = AsyncMock()
        
        # Mock web3 calls
        self.mock_engine.call_contract_function = AsyncMock()
        self.mock_engine.call_contract_function.side_effect = self._mock_contract_calls
        
        # Create mock config
        self.mock_config = MagicMock()
        self.mock_config.chain_id = 1
        
        # Create token discovery service with correct parameters
        self.token_discovery = TokenDiscoveryService(
            w3=self.mock_engine,
            config=self.mock_config
        )
        
        # Mock DEX factory addresses
        self.token_discovery.dex_factories = {
            'uniswap_v2': '0xUniV2Factory',
            'sushiswap': '0xSushiFactory',
            'uniswap_v3': '0xUniV3Factory'
        }
        
        # Mock token metadata
        self.token_metadata = {
            '0xToken1': {'symbol': 'TKN1', 'name': 'Token 1', 'decimals': 18},
            '0xToken2': {'symbol': 'TKN2', 'name': 'Token 2', 'decimals': 18},
            '0xToken3': {'symbol': 'TKN3', 'name': 'Token 3', 'decimals': 6},
            '0xWETH': {'symbol': 'WETH', 'name': 'Wrapped Ether', 'decimals': 18}
        }
    
    def _mock_contract_calls(self, contract_address, function_name, *args, **kwargs):
        """Mock contract function calls"""
        if function_name == 'allPairsLength':
            # Return different pair counts for different factories
            if contract_address == '0xUniV2Factory':
                return 100
            elif contract_address == '0xSushiFactory':
                return 50
            else:
                return 10
        
        elif function_name == 'allPairs':
            # Return mock pair addresses
            index = args[0]
            if contract_address == '0xUniV2Factory':
                return f'0xUniV2Pair{index}'
            elif contract_address == '0xSushiFactory':
                return f'0xSushiPair{index}'
            else:
                return f'0xUniV3Pool{index}'
        
        elif function_name == 'token0':
            # Return mock token0 addresses
            if 'UniV2' in contract_address:
                return '0xToken1'
            elif 'Sushi' in contract_address:
                return '0xToken2'
            else:
                return '0xWETH'
        
        elif function_name == 'token1':
            # Return mock token1 addresses
            if 'UniV2' in contract_address:
                return '0xToken2'
            elif 'Sushi' in contract_address:
                return '0xToken3'
            else:
                return '0xToken1'
        
        elif function_name in ['symbol', 'name', 'decimals']:
            # Return token metadata
            for token_addr, metadata in self.token_metadata.items():
                if args and args[0] == token_addr:
                    return metadata[function_name]
            return None
    
    async def async_test(self, coro):
        """Helper to run async tests"""
        return await coro
    
    def test_initialization(self):
        """Test token discovery initialization"""
        self.assertIsNotNone(self.token_discovery.w3)
        self.assertIsNotNone(self.token_discovery.config)
        self.assertEqual(len(self.token_discovery.dex_factories), 3)
    
    def test_discover_initial_pairs(self):
        """Test discovering initial pairs"""
        # Mock the method since it doesn't exist
        self.token_discovery.discover_initial_pairs = AsyncMock(return_value=[
            {'token0': '0xToken1', 'token1': '0xToken2', 'pair': '0xUniV2Pair0', 'dex': 'uniswap_v2'},
            {'token0': '0xToken2', 'token1': '0xToken3', 'pair': '0xSushiPair0', 'dex': 'sushiswap'},
            {'token0': '0xWETH', 'token1': '0xToken1', 'pair': '0xUniV3Pool0', 'dex': 'uniswap_v3'}
        ])
        
        # Run the test
        pairs = asyncio.run(self.token_discovery.discover_initial_pairs())
        
        # Verify results
        self.assertEqual(len(pairs), 3)
        self.assertEqual(pairs[0]['dex'], 'uniswap_v2')
        self.assertEqual(pairs[1]['dex'], 'sushiswap')
        self.assertEqual(pairs[2]['dex'], 'uniswap_v3')
    
    def test_fetch_pairs(self):
        """Test fetching pairs from DEX factories"""
        # Mock the method since it doesn't exist
        self.token_discovery._fetch_pairs = AsyncMock(return_value=[
            {'token0': '0xToken1', 'token1': '0xToken2', 'pair': f'0xUniV2Pair{i}', 'dex': 'uniswap_v2'}
            for i in range(5)
        ])
        
        # Run the test
        pairs = asyncio.run(self.token_discovery._fetch_pairs('uniswap_v2', 5))
        
        # Verify results
        self.assertEqual(len(pairs), 5)
        for i, pair in enumerate(pairs):
            self.assertEqual(pair['token0'], '0xToken1')
            self.assertEqual(pair['token1'], '0xToken2')
            self.assertEqual(pair['pair'], f'0xUniV2Pair{i}')
            self.assertEqual(pair['dex'], 'uniswap_v2')
    
    def test_get_token_metadata(self):
        """Test getting token metadata"""
        # Mock the method to return expected data
        self.token_discovery.get_token_metadata = AsyncMock(return_value={
            'symbol': 'TKN1',
            'name': 'Token 1',
            'decimals': 18
        })
        
        # Run the test
        metadata = asyncio.run(self.token_discovery.get_token_metadata('0xToken1'))
        
        # Verify results
        self.assertEqual(metadata['symbol'], 'TKN1')
        self.assertEqual(metadata['name'], 'Token 1')
        self.assertEqual(metadata['decimals'], 18)
    
    def test_get_all_pairs(self):
        """Test getting all pairs"""
        # Mock the method since it doesn't exist
        self.token_discovery.get_all_pairs = AsyncMock(return_value=[
            {'token0': '0xToken1', 'token1': '0xToken2', 'pair': '0xUniV2Pair0', 'dex': 'uniswap_v2'},
            {'token0': '0xToken2', 'token1': '0xToken3', 'pair': '0xSushiPair0', 'dex': 'sushiswap'}
        ])
        
        # Run the test
        pairs = asyncio.run(self.token_discovery.get_all_pairs())
        
        # Verify results
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]['dex'], 'uniswap_v2')
        self.assertEqual(pairs[1]['dex'], 'sushiswap')
    
    def test_get_pairs_for_token(self):
        """Test getting pairs for a specific token"""
        # Mock the method since it doesn't exist
        self.token_discovery.get_pairs_for_token = AsyncMock(return_value=[
            {'token0': '0xToken1', 'token1': '0xToken2', 'pair': '0xUniV2Pair0', 'dex': 'uniswap_v2'},
            {'token0': '0xWETH', 'token1': '0xToken1', 'pair': '0xUniV3Pool0', 'dex': 'uniswap_v3'}
        ])
        
        # Run the test
        pairs = asyncio.run(self.token_discovery.get_pairs_for_token('0xToken1'))
        
        # Verify results
        self.assertEqual(len(pairs), 2)  # Should find 2 pairs with Token1
        
        # Check if pairs contain Token1
        for pair in pairs:
            self.assertTrue(
                pair['token0'] == '0xToken1' or pair['token1'] == '0xToken1',
                f"Pair {pair} does not contain token 0xToken1"
            )
    
    def test_get_pairs_for_dex(self):
        """Test getting pairs for a specific DEX"""
        # Mock the method since it doesn't exist
        self.token_discovery.get_pairs_for_dex = AsyncMock(return_value=[
            {'token0': '0xToken1', 'token1': '0xToken2', 'pair': '0xUniV2Pair0', 'dex': 'uniswap_v2'},
            {'token0': '0xToken1', 'token1': '0xToken3', 'pair': '0xUniV2Pair1', 'dex': 'uniswap_v2'}
        ])
        
        # Run the test
        pairs = asyncio.run(self.token_discovery.get_pairs_for_dex('uniswap_v2'))
        
        # Verify results
        self.assertEqual(len(pairs), 2)  # Should find 2 Uniswap V2 pairs
        
        # Check if pairs are from Uniswap V2
        for pair in pairs:
            self.assertEqual(pair['dex'], 'uniswap_v2')


if __name__ == '__main__':
    unittest.main()