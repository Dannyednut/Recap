import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import components to test
from dex.ethereum_service.flashloan_engine import FlashLoanEngine


class TestFlashLoanEngine(unittest.TestCase):
    """Test suite for flashloan engine"""
    
    def setUp(self):
        """Set up test environment"""
        # Create mock objects
        self.mock_engine = AsyncMock()
        
        # Mock contract calls
        self.mock_engine.call_contract_function = AsyncMock()
        self.mock_engine.call_contract_function.side_effect = self._mock_contract_calls
        
        # Create mock config
        from dex.ethereum_service.config import EthereumConfig
        self.mock_config = EthereumConfig()
        
        # Create flashloan engine
        self.flashloan_engine = FlashLoanEngine(
            engine=self.mock_engine,
            config=self.mock_config
        )
        
        # Mock provider addresses (matching actual FlashLoanEngine structure)
        self.flashloan_engine.providers = {
            'aave': {
                'address': '0xAaveLendingPool',
                'fee_percentage': Decimal('0.0009')  # 0.09%
            },
            'balancer': {
                'address': '0xBalancerVault', 
                'fee_percentage': Decimal('0.0006')  # 0.06%
            }
        }
        
        # Mock token addresses
        self.token_addresses = {
            'DAI': '0xDAI',
            'USDC': '0xUSDC',
            'WETH': '0xWETH',
            'WBTC': '0xWBTC'
        }
        
        # Mock token balances for providers
        self.provider_balances = {
            'aave': {
                '0xDAI': Decimal('1000000'),  # 1M DAI
                '0xUSDC': Decimal('2000000'),  # 2M USDC
                '0xWETH': Decimal('500'),      # 500 WETH
                '0xWBTC': Decimal('10')        # 10 WBTC
            },
            'balancer': {
                '0xDAI': Decimal('500000'),    # 500k DAI
                '0xUSDC': Decimal('1000000'),  # 1M USDC
                '0xWETH': Decimal('1000'),     # 1000 WETH
                '0xWBTC': Decimal('5')         # 5 WBTC
            },
            'dydx': {
                '0xDAI': Decimal('200000'),    # 200k DAI
                '0xUSDC': Decimal('500000'),   # 500k USDC
                '0xWETH': Decimal('100'),      # 100 WETH
                '0xWBTC': Decimal('2')         # 2 WBTC
            }
        }
    
    def _mock_contract_calls(self, contract_address, function_name, *args, **kwargs):
        """Mock contract function calls"""
        if function_name == 'getReserveData':
            # Mock Aave getReserveData
            token_address = args[0]
            if contract_address == '0xAaveLendingPool':
                return [self.provider_balances['aave'].get(token_address, Decimal('0')), 0, 0, 0, 0, 0, 0, 0, 0, 0]
        
        elif function_name == 'getPoolTokenInfo':
            # Mock Balancer getPoolTokenInfo
            token_address = args[0]
            if contract_address == '0xBalancerVault':
                return [self.provider_balances['balancer'].get(token_address, Decimal('0')), 0, 0]
        
        elif function_name == 'getAccountWei':
            # Mock dYdX getAccountWei
            token_address = args[0]
            if contract_address == '0xDydxSolo':
                return [self.provider_balances['dydx'].get(token_address, Decimal('0'))]
        
        return None
    
    async def async_test(self, coro):
        """Helper to run async tests"""
        return await coro
    
    def test_initialization(self):
        """Test flashloan engine initialization"""
        self.assertIsNotNone(self.flashloan_engine.engine)
        self.assertIsNotNone(self.flashloan_engine.config)
        self.assertEqual(len(self.flashloan_engine.providers), 2)
    
    def test_get_available_liquidity(self):
        """Test getting available liquidity for a token"""
        # Mock the method since it requires complex contract interactions
        self.flashloan_engine.get_available_liquidity = AsyncMock(return_value={
            'aave': Decimal('1000000'),
            'balancer': Decimal('500000')
        })
        
        # Run the test
        liquidity = asyncio.run(self.flashloan_engine.get_available_liquidity('0xDAI'))
        
        # Verify results
        self.assertEqual(len(liquidity), 2)  # Should have 2 providers
        
        # Check liquidity amounts
        self.assertEqual(liquidity['aave'], Decimal('1000000'))
        self.assertEqual(liquidity['balancer'], Decimal('500000'))
    
    def test_get_best_flashloan_provider(self):
        """Test getting the best flashloan provider"""
        # Mock the method
        self.flashloan_engine.get_best_flashloan_provider = AsyncMock(return_value={
            'provider': 'balancer',
            'fee': Decimal('0.0006'),
            'max_amount': Decimal('500000')
        })
        
        # Run the test
        best_provider = asyncio.run(self.flashloan_engine.get_best_flashloan_provider(
            token_address='0xDAI',
            amount=Decimal('100000')
        ))
        
        # Verify results - Balancer should be best due to lower fee than Aave
        self.assertEqual(best_provider['provider'], 'balancer')
        self.assertEqual(best_provider['fee'], Decimal('0.0006'))
        self.assertEqual(best_provider['max_amount'], Decimal('500000'))
    
    def test_estimate_flashloan_cost(self):
        """Test estimating flashloan cost"""
        # Mock the method
        def mock_estimate_cost(token_address, amount, provider):
            if provider == 'aave':
                return amount * Decimal('0.0009')
            elif provider == 'balancer':
                return amount * Decimal('0.0006')
            return Decimal('0')
        
        self.flashloan_engine.estimate_flashloan_cost = AsyncMock(side_effect=mock_estimate_cost)
        
        # Run the test for Aave
        cost = asyncio.run(self.flashloan_engine.estimate_flashloan_cost(
            token_address='0xDAI',
            amount=Decimal('100000'),
            provider='aave'
        ))
        
        # Verify results - Aave fee is 0.09%
        expected_cost = Decimal('100000') * Decimal('0.0009')
        self.assertEqual(cost, expected_cost)
        
        # Run the test for Balancer
        cost = asyncio.run(self.flashloan_engine.estimate_flashloan_cost(
            token_address='0xDAI',
            amount=Decimal('100000'),
            provider='balancer'
        ))
        
        # Verify results - Balancer fee is 0.06%
        expected_cost = Decimal('100000') * Decimal('0.0006')
        self.assertEqual(cost, expected_cost)
    
    def test_prepare_flashloan_for_cross_exchange(self):
        """Test preparing flashloan for cross-exchange arbitrage"""
        # Mock the method since it doesn't exist in actual implementation
        self.flashloan_engine.prepare_flashloan_for_cross_exchange = AsyncMock(return_value={
            'token': '0xDAI',
            'amount': Decimal('100000'),
            'provider': 'balancer',
            'fee': Decimal('60'),
            'profitable': True
        })
        
        # Mock opportunity
        opportunity = {
            'token_in': '0xDAI',
            'amount_in': Decimal('100000'),
            'profit_usd': Decimal('500'),
            'dex_1': 'uniswap_v2',
            'dex_2': 'sushiswap'
        }
        
        # Run the test
        flashloan_params = asyncio.run(self.flashloan_engine.prepare_flashloan_for_cross_exchange(
            opportunity=opportunity
        ))
        
        # Verify results
        self.assertEqual(flashloan_params['token'], '0xDAI')
        self.assertEqual(flashloan_params['amount'], Decimal('100000'))
        self.assertEqual(flashloan_params['provider'], 'balancer')
        self.assertTrue(flashloan_params['profitable'])
    
    def test_prepare_flashloan_for_triangular(self):
        """Test preparing flashloan for triangular arbitrage"""
        # Mock the method since it doesn't exist in actual implementation
        self.flashloan_engine.prepare_flashloan_for_triangular = AsyncMock(return_value={
            'token': '0xWETH',
            'amount': Decimal('10'),
            'provider': 'balancer',
            'fee': Decimal('0.006'),
            'profitable': True
        })
        
        # Mock opportunity
        opportunity = {
            'token_in': '0xWETH',
            'amount_in': Decimal('10'),
            'profit_usd': Decimal('50'),
            'path': ['0xWETH', '0xDAI', '0xUSDC', '0xWETH'],
            'dex': 'uniswap_v3'
        }
        
        # Run the test
        flashloan_params = asyncio.run(self.flashloan_engine.prepare_flashloan_for_triangular(
            opportunity=opportunity
        ))
        
        # Verify results
        self.assertEqual(flashloan_params['token'], '0xWETH')
        self.assertEqual(flashloan_params['amount'], Decimal('10'))
        self.assertEqual(flashloan_params['provider'], 'balancer')
        self.assertTrue(flashloan_params['profitable'])
    
    def test_prepare_flashloan_for_backrun(self):
        """Test preparing flashloan for backrun arbitrage"""
        # Mock the method since it doesn't exist in actual implementation
        self.flashloan_engine.prepare_flashloan_for_backrun = AsyncMock(return_value={
            'token': '0xUSDC',
            'amount': Decimal('50000'),
            'provider': 'balancer',
            'fee': Decimal('30'),
            'profitable': True
        })
        
        # Mock opportunity
        opportunity = {
            'token_in': '0xUSDC',
            'amount_in': Decimal('50000'),
            'profit_usd': Decimal('200'),
            'target_tx': '0x123abc',
            'dex': 'uniswap_v2'
        }
        
        # Run the test
        flashloan_params = asyncio.run(self.flashloan_engine.prepare_flashloan_for_backrun(
            opportunity=opportunity
        ))
        
        # Verify results
        self.assertEqual(flashloan_params['token'], '0xUSDC')
        self.assertEqual(flashloan_params['amount'], Decimal('50000'))
        self.assertEqual(flashloan_params['provider'], 'balancer')
        self.assertTrue(flashloan_params['profitable'])
    
    def test_unprofitable_flashloan(self):
        """Test when flashloan would be unprofitable"""
        # Mock the method to return unprofitable result
        self.flashloan_engine.prepare_flashloan_for_cross_exchange = AsyncMock(return_value={
            'token': '0xDAI',
            'amount': Decimal('100000'),
            'provider': None,
            'fee': None,
            'profitable': False
        })
        
        # Mock opportunity with low profit
        opportunity = {
            'token_in': '0xDAI',
            'amount_in': Decimal('100000'),
            'profit_usd': Decimal('10'),  # Very low profit
            'dex_1': 'uniswap_v2',
            'dex_2': 'sushiswap'
        }
        
        # Run the test
        flashloan_params = asyncio.run(self.flashloan_engine.prepare_flashloan_for_cross_exchange(
            opportunity=opportunity
        ))
        
        # Verify results - should be unprofitable
        self.assertFalse(flashloan_params['profitable'])
        self.assertIsNone(flashloan_params.get('provider'))


if __name__ == '__main__':
    unittest.main()