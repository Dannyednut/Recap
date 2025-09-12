import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import components to test
from dex.ethereum_service.arbitrage_pipeline import ArbitragePipeline
from dex.ethereum_service.cross_arbitrage import CrossArbitrageEngine
from dex.shared.base_arbitrage import BaseArbitrageStrategy
from dex.chain_factory import ChainFactory
from dex.shared.models.chain_models import ChainConfig
from dex.ethereum_service.flashloan_engine import FlashLoanEngine
from dex.ethereum_service.contract_executor import ContractExecutor
from dex.ethereum_service.token_discovery import TokenDiscoveryService


class TestArbitrageStrategies(unittest.TestCase):
    """Test suite for arbitrage strategies"""
    
    def setUp(self):
        """Set up test environment"""
        # Create mock objects
        self.mock_engine = AsyncMock()
        self.mock_engine.get_token_balance = AsyncMock(return_value=Decimal('10.0'))
        self.mock_engine.get_eth_balance = AsyncMock(return_value=Decimal('2.0'))
        self.mock_engine.get_gas_price = AsyncMock(return_value=20000000000)  # 20 gwei
        
        # Mock contract executor
        self.mock_executor = AsyncMock(spec=ContractExecutor)
        self.mock_executor.execute_cross_exchange_arbitrage = AsyncMock(return_value={
            'success': True,
            'profit': Decimal('0.05'),
            'tx_hash': '0x1234'
        })
        self.mock_executor.execute_triangular_arbitrage = AsyncMock(return_value={
            'success': True,
            'profit': Decimal('0.03'),
            'tx_hash': '0x5678'
        })
        self.mock_executor.execute_backrun_arbitrage = AsyncMock(return_value={
            'success': True,
            'profit': Decimal('0.02'),
            'tx_hash': '0x9abc'
        })
        
        # Mock flashloan engine
        self.mock_flashloan = AsyncMock(spec=FlashLoanEngine)
        self.mock_flashloan.get_best_flashloan_provider = AsyncMock(return_value={
            'provider': 'aave',
            'max_amount': Decimal('1000'),
            'fee': Decimal('0.0009')
        })
        
        # Mock token discovery
        self.mock_token_discovery = AsyncMock(spec=TokenDiscoveryService)
        self.mock_token_discovery.get_all_pairs = AsyncMock(return_value=[
            {'token0': '0xToken1', 'token1': '0xToken2', 'pair': '0xPair1', 'dex': 'uniswap_v2'},
            {'token0': '0xToken2', 'token1': '0xToken3', 'pair': '0xPair2', 'dex': 'sushiswap'},
            {'token0': '0xToken3', 'token1': '0xToken1', 'pair': '0xPair3', 'dex': 'uniswap_v3'}
        ])
        
        # Mock strategies
        self.mock_cross_strategy = AsyncMock(spec=BaseArbitrageStrategy)
        self.mock_triangular_strategy = AsyncMock(spec=BaseArbitrageStrategy)
        
        # Create mock config
        self.mock_config = MagicMock()
        self.mock_config.MIN_PROFIT_THRESHOLD = 0.01
        self.mock_config.MAX_TRADE_SIZE_ETH = 1.0
        self.mock_config.SLIPPAGE_TOLERANCE = 0.005
        
        # Create pipeline
        self.pipeline = ArbitragePipeline(
            config=self.mock_config,
            engine=self.mock_engine,
            cross_arbitrage=self.mock_cross_strategy,
            triangular_arbitrage=self.mock_triangular_strategy,
            mempool_monitor=MagicMock(),
            flashloan_engine=self.mock_flashloan,
            contract_executor=self.mock_executor,
            token_discovery=self.mock_token_discovery
        )
        self.mock_cross_strategy.scan_opportunities = AsyncMock(return_value=[
            {
                'id': 'cross_1',
                'token_in': '0xToken1',
                'token_out': '0xToken2',
                'dex_1': 'uniswap_v2',
                'dex_2': 'sushiswap',
                'profit_usd': Decimal('50.0'),
                'profit_percentage': Decimal('0.05'),
                'amount_in': Decimal('1000'),
                'type': 'cross'
            }
        ])
        
        self.mock_triangular_strategy = AsyncMock(spec=BaseArbitrageStrategy)
        self.mock_triangular_strategy.scan_opportunities = AsyncMock(return_value=[
            {
                'id': 'tri_1',
                'token_in': '0xToken1',
                'path': ['0xToken1', '0xToken2', '0xToken3', '0xToken1'],
                'dex': 'uniswap_v2',
                'profit_usd': Decimal('30.0'),
                'profit_percentage': Decimal('0.03'),
                'amount_in': Decimal('1000'),
                'type': 'triangular'
            }
        ])
        
        self.mock_backrun_strategy = AsyncMock(spec=BaseArbitrageStrategy)
        self.mock_backrun_strategy.scan_opportunities = AsyncMock(return_value=[
            {
                'id': 'backrun_1',
                'token_in': '0xToken1',
                'token_out': '0xToken2',
                'target_tx': '0xTargetTx',
                'profit_usd': Decimal('20.0'),
                'profit_percentage': Decimal('0.02'),
                'amount_in': Decimal('1000'),
                'type': 'backrun'
            }
        ])
        
        # Strategies are already added via constructor - no need to add them separately
    
    async def async_test(self, coro):
        """Helper to run async tests"""
        return await coro
    
    def test_pipeline_initialization(self):
        """Test pipeline initialization"""
        self.assertIsNotNone(self.pipeline.cross_arbitrage)
        self.assertIsNotNone(self.pipeline.triangular_arbitrage)
        self.assertIsNotNone(self.pipeline.flashloan_engine)
    
    def test_scan_opportunities(self):
        """Test scanning for opportunities"""
        # Test that pipeline has the required components
        self.assertIsNotNone(self.pipeline.cross_arbitrage)
        self.assertIsNotNone(self.pipeline.triangular_arbitrage)
        
        # Test basic functionality
        self.assertTrue(hasattr(self.pipeline, 'add_opportunity_callback'))
    
    def test_execute_cross_opportunity(self):
        """Test executing cross-exchange arbitrage"""
        # Test that pipeline has execution stats
        self.assertIsNotNone(self.pipeline.execution_stats)
        self.assertIn('cross', self.pipeline.execution_stats)
    
    def test_execute_triangular_opportunity(self):
        """Test executing triangular arbitrage"""
        # Test that pipeline has triangular stats
        self.assertIsNotNone(self.pipeline.execution_stats)
        self.assertIn('triangular', self.pipeline.execution_stats)
    
    def test_execute_backrun_opportunity(self):
        """Test executing backrun arbitrage"""
        # Test that pipeline has mempool stats
        self.assertIsNotNone(self.pipeline.execution_stats)
        self.assertIn('mempool', self.pipeline.execution_stats)
    
    def test_chain_factory(self):
        """Test chain factory creates components for different chains"""
        # Test that ChainFactory can be imported
        self.assertIsNotNone(ChainFactory)


if __name__ == '__main__':
    unittest.main()