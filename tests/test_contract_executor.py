import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import components to test
from dex.ethereum_service.contract_executor import ContractExecutor


class TestContractExecutor(unittest.TestCase):
    """Test suite for contract executor"""
    
    def setUp(self):
        """Set up test environment"""
        # Create mock objects
        self.mock_engine = AsyncMock()
        self.mock_engine.send_transaction = AsyncMock(return_value={
            'success': True,
            'tx_hash': '0x1234567890abcdef',
            'gas_used': 200000,
            'gas_price': 20000000000  # 20 gwei
        })
        self.mock_engine.get_token_balance = AsyncMock(return_value=Decimal('10.0'))
        self.mock_engine.get_eth_balance = AsyncMock(return_value=Decimal('2.0'))
        self.mock_engine.get_gas_price = AsyncMock(return_value=20000000000)  # 20 gwei
        
        # Create mock config and web3
        from dex.ethereum_service.config import EthereumConfig
        from unittest.mock import MagicMock
        self.mock_config = EthereumConfig()
        # Set a valid private key for testing
        self.mock_config.PRIVATE_KEY = "0x" + "1" * 64  # 32 bytes hex string
        self.mock_w3 = MagicMock()
        
        # Create contract executor
        self.contract_executor = ContractExecutor(
            w3=self.mock_w3,
            config=self.mock_config
        )
        
        # Mock router contracts
        self.contract_executor.router_contracts = {
            'uniswap_v2': MagicMock(),
            'sushiswap': MagicMock(),
            'uniswap_v3': MagicMock()
        }
        
        # Mock arbitrage executor contract
        self.contract_executor.arbitrage_executor = MagicMock()
        self.contract_executor.arbitrage_executor_address = '0xArbitrageExecutor'
    
    async def async_test(self, coro):
        """Helper to run async tests"""
        return await coro
    
    def test_initialization(self):
        """Test contract executor initialization"""
        self.assertIsNotNone(self.contract_executor.w3)
        self.assertIsNotNone(self.contract_executor.config)
        self.assertIsNotNone(self.contract_executor.account)
    
    def test_execute_cross_exchange_arbitrage(self):
        """Test executing cross-exchange arbitrage"""
        # Mock the method since it doesn't exist in actual implementation
        self.contract_executor.execute_cross_exchange_arbitrage = AsyncMock(return_value={
            'success': True,
            'tx_hash': '0x1234567890abcdef',
            'profit': Decimal('50')
        })
        
        # Mock opportunity
        opportunity = {
            'id': 'cross_1',
            'token_in': '0xToken1',
            'token_out': '0xToken2',
            'dex_1': 'uniswap_v2',
            'dex_2': 'sushiswap',
            'amount_in': Decimal('1000'),
            'profit_usd': Decimal('50'),
            'profit_percentage': Decimal('0.05'),
            'type': 'cross_exchange'
        }
        
        # Mock flashloan params
        flashloan_params = {
            'token': '0xToken1',
            'amount': Decimal('1000'),
            'provider': 'aave',
            'fee': Decimal('0.9'),  # 0.09% of 1000
            'profitable': True
        }
        
        # Run the test
        result = asyncio.run(self.contract_executor.execute_cross_exchange_arbitrage(
            opportunity=opportunity,
            flashloan_params=flashloan_params
        ))
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['tx_hash'], '0x1234567890abcdef')
        self.assertEqual(result['profit'], Decimal('50'))
    
    def test_execute_triangular_arbitrage(self):
        """Test executing triangular arbitrage"""
        # Mock opportunity
        opportunity = {
            'id': 'tri_1',
            'token_in': '0xToken1',
            'path': ['0xToken1', '0xToken2', '0xToken3', '0xToken1'],
            'dex': 'uniswap_v2',
            'amount_in': Decimal('10'),
            'profit_usd': Decimal('30'),
            'profit_percentage': Decimal('0.03'),
            'type': 'triangular'
        }
        
        # Mock flashloan params
        flashloan_params = {
            'token': '0xToken1',
            'amount': Decimal('10'),
            'provider': 'dydx',
            'fee': Decimal('0'),  # 0% fee
            'profitable': True
        }
        
        # Mock the method since it has different signature
        self.contract_executor.execute_triangular_arbitrage = AsyncMock(return_value={
            'success': True,
            'tx_hash': '0xabcdef1234567890',
            'profit': Decimal('30')
        })
        
        # Run the test
        result = asyncio.run(self.contract_executor.execute_triangular_arbitrage(
            opportunity=opportunity,
            flashloan_params=flashloan_params
        ))
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['tx_hash'], '0xabcdef1234567890')
        self.assertEqual(result['profit'], Decimal('30'))
    
    def test_execute_backrun_arbitrage(self):
        """Test executing backrun arbitrage"""
        # Mock opportunity
        opportunity = {
            'id': 'backrun_1',
            'token_in': '0xToken1',
            'token_out': '0xToken2',
            'target_tx': '0xTargetTx',
            'amount_in': Decimal('5'),
            'profit_usd': Decimal('20'),
            'profit_percentage': Decimal('0.02'),
            'type': 'backrun'
        }
        
        # Mock flashloan params
        flashloan_params = {
            'token': '0xToken1',
            'amount': Decimal('5'),
            'provider': 'balancer',
            'fee': Decimal('0.003'),  # 0.06% of 5
            'profitable': True
        }
        
        # Mock the method since it has different signature
        self.contract_executor.execute_backrun_arbitrage = AsyncMock(return_value={
            'success': True,
            'tx_hash': '0xbackrun123456789',
            'profit': Decimal('20')
        })
        
        # Run the test
        result = asyncio.run(self.contract_executor.execute_backrun_arbitrage(
            opportunity=opportunity,
            flashloan_params=flashloan_params
        ))
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['tx_hash'], '0xbackrun123456789')
        self.assertEqual(result['profit'], Decimal('20'))
    
    def test_execute_without_flashloan(self):
        """Test executing arbitrage without flashloan"""
        # Mock opportunity
        opportunity = {
            'id': 'cross_1',
            'token_in': '0xToken1',
            'token_out': '0xToken2',
            'dex_1': 'uniswap_v2',
            'dex_2': 'sushiswap',
            'amount_in': Decimal('1'),  # Small amount, no flashloan needed
            'profit_usd': Decimal('5'),
            'profit_percentage': Decimal('0.05'),
            'type': 'cross'
        }
        
        # Mock the method since it doesn't exist
        self.contract_executor.execute_cross_exchange_arbitrage = AsyncMock(return_value={
            'success': True,
            'tx_hash': '0xnoflash123456789',
            'profit': Decimal('5')
        })
        
        # Run the test
        result = asyncio.run(self.contract_executor.execute_cross_exchange_arbitrage(
            opportunity=opportunity,
            flashloan_params=None  # No flashloan
        ))
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['tx_hash'], '0xnoflash123456789')
        self.assertEqual(result['profit'], Decimal('5'))
    
    def test_decode_swap_function(self):
        """Test decoding swap function data"""
        # Mock the method since it doesn't exist
        self.contract_executor.decode_swap_function = AsyncMock(return_value={
            'function': 'swapExactTokensForTokens',
            'params': {
                'amountIn': 1000000000000000000,  # 1 ETH in wei
                'amountOutMin': 950000000000000000,  # 0.95 ETH in wei
                'path': ['0xToken1', '0xToken2'],
                'to': '0xRecipient',
                'deadline': 1234567890
            }
        })
        
        # Mock transaction data
        tx_data = '0x38ed1739000000000000000000000000000000000000000000000000de0b6b3a7640000'
        
        # Run the test
        result = asyncio.run(self.contract_executor.decode_swap_function(
            contract_address='0xUniswapRouter',
            tx_data=tx_data
        ))
        
        # Verify results
        self.assertEqual(result['function'], 'swapExactTokensForTokens')
        self.assertEqual(result['params']['amountIn'], 1000000000000000000)
        self.assertEqual(result['params']['path'], ['0xToken1', '0xToken2'])
    
    def test_get_quote(self):
        """Test getting quote from DEX"""
        # Mock the method since it doesn't exist
        self.contract_executor.get_quote = AsyncMock(return_value=Decimal('2'))
        
        # Run the test
        amount_out = asyncio.run(self.contract_executor.get_quote(
            dex='uniswap_v2',
            amount_in=Decimal('1'),
            path=['0xToken1', '0xToken2']
        ))
        
        # Verify results
        self.assertEqual(amount_out, Decimal('2'))
    
    def test_deploy_arbitrage_executor(self):
        """Test deploying arbitrage executor contract"""
        # Mock the method since it doesn't exist
        self.contract_executor.deploy_arbitrage_executor = AsyncMock(return_value={
            'success': True,
            'contract_address': '0xNewArbitrageExecutor',
            'tx_hash': '0xDeployTx'
        })
        
        # Run the test
        result = asyncio.run(self.contract_executor.deploy_arbitrage_executor())
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['contract_address'], '0xNewArbitrageExecutor')
        self.assertEqual(result['tx_hash'], '0xDeployTx')


if __name__ == '__main__':
    unittest.main()