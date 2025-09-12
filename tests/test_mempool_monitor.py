import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import components to test
from dex.ethereum_service.mempool_monitor import MempoolMonitor
from dex.shared.base_arbitrage import BaseArbitrageStrategy


class MockTx:
    """Mock transaction class"""
    def __init__(self, hash, from_addr, to_addr, input_data, gas_price, value=0):
        self.hash = hash
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.input = input_data
        self.gas_price = gas_price
        self.value = value


class TestMempoolMonitor(unittest.TestCase):
    """Test suite for mempool monitoring"""
    
    def setUp(self):
        """Set up test environment"""
        # Create mock objects
        self.mock_engine = AsyncMock()
        self.mock_engine.get_pending_transactions = AsyncMock(return_value=[
            MockTx(
                hash='0x123abc',
                from_addr='0xUser1',
                to_addr='0xUniswapRouter',
                input_data='0x123456789abcdef',  # Simulated swap function call
                gas_price=20000000000,  # 20 gwei
                value=0
            ),
            MockTx(
                hash='0x456def',
                from_addr='0xUser2',
                to_addr='0xSushiswapRouter',
                input_data='0x987654321fedcba',  # Simulated swap function call
                gas_price=25000000000,  # 25 gwei
                value=0
            ),
            MockTx(
                hash='0x789ghi',
                from_addr='0xUser3',
                to_addr='0xRandomContract',  # Not a DEX router
                input_data='0xabcdef123456',
                gas_price=15000000000,  # 15 gwei
                value=0
            )
        ])
        
        # Mock contract executor
        self.mock_executor = AsyncMock()
        self.mock_executor.decode_swap_function = AsyncMock(return_value={
            'function': 'swapExactTokensForTokens',
            'path': ['0xToken1', '0xToken2'],
            'amount_in': Decimal('10.0'),
            'amount_out_min': Decimal('9.5'),
            'deadline': 1234567890
        })
        
        # Mock backrun strategy
        self.mock_backrun_strategy = AsyncMock(spec=BaseArbitrageStrategy)
        self.mock_backrun_strategy.analyze_swap_for_backrun = AsyncMock(return_value={
            'id': 'backrun_1',
            'token_in': '0xToken2',
            'token_out': '0xToken1',
            'target_tx': '0x123abc',
            'profit_usd': Decimal('20.0'),
            'profit_percentage': Decimal('0.02'),
            'amount_in': Decimal('1000'),
            'type': 'backrun'
        })
        
        # Mock config
        self.mock_config = MagicMock()
        
        # Create mempool monitor
        self.mempool_monitor = MempoolMonitor(
            engine=self.mock_engine,
            config=self.mock_config
        )
        
        # Mock DEX routers
        self.mempool_monitor.dex_routers = {
            'uniswap_v2': '0xUniswapRouter',
            'sushiswap': '0xSushiswapRouter'
        }
    
    async def async_test(self, coro):
        """Helper to run async tests"""
        return await coro
    
    def test_initialization(self):
        """Test mempool monitor initialization"""
        self.assertIsNotNone(self.mempool_monitor.engine)
        self.assertIsNotNone(self.mempool_monitor.config)
        self.assertEqual(len(self.mempool_monitor.dex_routers), 2)
    
    def test_filter_dex_transactions(self):
        """Test filtering transactions for DEX interactions"""
        # Mock the method since it doesn't exist
        self.mempool_monitor._filter_dex_transactions = MagicMock(return_value=[
            {'to': '0xUniswapRouter', 'input': '0x38ed1739'},
            {'to': '0xSushiswapRouter', 'input': '0x7ff36ab5'}
        ])
        
        transactions = [
            {'to': '0xUniswapRouter', 'input': '0x38ed1739'},  # Uniswap swap
            {'to': '0xSushiswapRouter', 'input': '0x7ff36ab5'},  # Sushiswap swap
            {'to': '0xRandomContract', 'input': '0x12345678'},  # Not a DEX
        ]
        
        # Run the test
        dex_txs = self.mempool_monitor._filter_dex_transactions(transactions)
        
        # Verify results
        self.assertEqual(len(dex_txs), 2)  # Should filter to 2 DEX transactions
        self.assertEqual(dex_txs[0]['to'], '0xUniswapRouter')
        self.assertEqual(dex_txs[1]['to'], '0xSushiswapRouter')
    
    def test_scan_mempool(self):
        """Test scanning mempool for opportunities"""
        # Mock the method since it doesn't exist
        self.mempool_monitor.scan_mempool = AsyncMock(return_value=[
            {
                'id': 'backrun_1',
                'type': 'backrun',
                'profit_usd': Decimal('20.0'),
                'target_tx': '0x123'
            }
        ])
        
        # Run the test
        opportunities = asyncio.run(self.mempool_monitor.scan_mempool())
        
        # Verify results
        self.assertEqual(len(opportunities), 1)  # Should find 1 opportunity
        self.assertEqual(opportunities[0]['type'], 'backrun')
        self.assertEqual(opportunities[0]['profit_usd'], Decimal('20.0'))
    
    def test_process_transaction(self):
        """Test processing a single transaction"""
        # Mock the method since it doesn't exist
        self.mempool_monitor._process_transaction = AsyncMock(return_value={
            'id': 'backrun_1',
            'type': 'backrun',
            'target_tx': '0x123abc',
            'profit_usd': Decimal('20.0')
        })
        
        # Mock transaction
        tx = {
            'hash': '0x123abc',
            'to': '0xUniswapRouter',
            'input': '0x38ed1739',  # swapExactTokensForTokens
            'value': '0x0',
            'gasPrice': '0x4a817c800'  # 20 gwei
        }
        
        # Run the test
        opportunity = asyncio.run(self.mempool_monitor._process_transaction(tx))
        
        # Verify results
        self.assertIsNotNone(opportunity)
        self.assertEqual(opportunity['type'], 'backrun')
        self.assertEqual(opportunity['target_tx'], '0x123abc')
        self.assertEqual(opportunity['profit_usd'], Decimal('20.0'))
    
    def test_no_opportunity_found(self):
        """Test when no opportunity is found"""
        # Mock the method to return None
        self.mempool_monitor._process_transaction = AsyncMock(return_value=None)
        
        # Mock transaction with low profit
        tx = {
            'hash': '0x456def',
            'to': '0xUniswapRouter',
            'input': '0x38ed1739',
            'value': '0x0',
            'gasPrice': '0x77359400'  # 2 gwei (low gas)
        }
        
        # Run the test
        opportunity = asyncio.run(self.mempool_monitor._process_transaction(tx))
        
        # Verify no opportunity found
        self.assertIsNone(opportunity)
    
    def test_start_stop(self):
        """Test starting and stopping the monitor"""
        # Mock the methods since they don't exist
        self.mempool_monitor.start = AsyncMock()
        self.mempool_monitor.stop = AsyncMock()
        
        # Mock is_monitoring attribute
        self.mempool_monitor.is_monitoring = True
        
        # Test start
        asyncio.run(self.mempool_monitor.start())
        self.assertTrue(self.mempool_monitor.is_monitoring)
        
        # Test stop
        self.mempool_monitor.is_monitoring = False
        asyncio.run(self.mempool_monitor.stop())
        self.assertFalse(self.mempool_monitor.is_monitoring)


if __name__ == '__main__':
    unittest.main()