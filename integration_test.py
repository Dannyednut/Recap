#!/usr/bin/env python3
"""
Integration Quality Test for ArbitrageWise-Refined
Tests cross-service compatibility and integration quality
"""

import asyncio
import logging
import sys
import os
from decimal import Decimal
from typing import Dict, Any, List

# Add project paths
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), 'dex', 'shared'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntegrationTester:
    """Test integration quality across all blockchain services"""
    
    def __init__(self):
        self.test_results = {}
        self.errors = []
        
    async def run_all_tests(self):
        """Run comprehensive integration tests"""
        logger.info("🧪 Starting ArbitrageWise Integration Quality Tests")
        
        tests = [
            ("Import Tests", self.test_imports),
            ("Service Initialization", self.test_service_initialization),
            ("Price Aggregator Integration", self.test_price_aggregator),
            ("Cross-Chain Compatibility", self.test_cross_chain_compatibility),
            ("Engine Method Compatibility", self.test_engine_methods),
            ("Configuration Consistency", self.test_configuration_consistency)
        ]
        
        for test_name, test_func in tests:
            try:
                logger.info(f"Running {test_name}...")
                result = await test_func()
                self.test_results[test_name] = result
                status = "✅ PASS" if result["success"] else "❌ FAIL"
                logger.info(f"{test_name}: {status}")
                if not result["success"]:
                    logger.error(f"  Error: {result.get('error', 'Unknown error')}")
            except Exception as e:
                self.test_results[test_name] = {"success": False, "error": str(e)}
                logger.error(f"{test_name}: ❌ FAIL - {e}")
        
        self.print_summary()
        
    async def test_imports(self) -> Dict[str, Any]:
        """Test if all services can be imported without errors"""
        try:
            # Test Solana service imports
            from dex.solana_service.arbitrage import SolanaArbitrageService
            from dex.solana_service.engine import SolanaEngine
            from dex.solana_service.config import SolanaConfig
            
            # Test Ethereum service imports
            from dex.ethereum_service.arbitrage import EthereumArbitrageService
            from dex.ethereum_service.engine import EthereumEngine
            from dex.ethereum_service.config import EthereumConfig
            
            # Test BSC service imports
            from dex.bsc_service.arbitrage import BSCArbitrageService
            from dex.bsc_service.engine import BSCEngine
            from dex.bsc_service.config import BSCConfig
            
            # Test Polygon service imports
            from dex.polygon_service.arbitrage import PolygonArbitrageService
            from dex.polygon_service.engine import PolygonEngine
            from dex.polygon_service.config import PolygonConfig
            
            # Test shared modules
            from dex.shared.price_aggregator import EVMPriceAggregator
            from dex.shared.interfaces.base_engine import BaseEngine, BaseArbitrageEngine
            
            # Test ExecutionResult import separately to debug the issue
            try:
                from dex.shared.models.arbitrage_models import ArbitrageOpportunity, ExecutionResult
            except NameError as ne:
                # Try importing with explicit path
                import sys
                import os
                dex_path = os.path.join(os.getcwd(), 'dex')
                if dex_path not in sys.path:
                    sys.path.insert(0, dex_path)
                from shared.models.arbitrage_models import ArbitrageOpportunity, ExecutionResult
            
            return {"success": True, "message": "All imports successful"}
            
        except Exception as e:
            return {"success": False, "error": f"Import failed: {e}"}
    
    async def test_service_initialization(self) -> Dict[str, Any]:
        """Test if services can be initialized without RPC connections"""
        try:
            from dex.solana_service.config import SolanaConfig
            from dex.ethereum_service.config import EthereumConfig
            from dex.bsc_service.config import BSCConfig
            from dex.polygon_service.config import PolygonConfig
            
            # Test config initialization
            configs = {
                "solana": SolanaConfig(),
                "ethereum": EthereumConfig(),
                "bsc": BSCConfig(),
                "polygon": PolygonConfig()
            }
            
            # Verify configs have required attributes
            required_attrs = ["RPC_URL", "PRIVATE_KEY"]
            for chain, config in configs.items():
                for attr in required_attrs:
                    if not hasattr(config, attr):
                        return {"success": False, "error": f"{chain} config missing {attr}"}
            
            return {"success": True, "message": "All service configs initialized"}
            
        except Exception as e:
            return {"success": False, "error": f"Service initialization failed: {e}"}
    
    async def test_price_aggregator(self) -> Dict[str, Any]:
        """Test price aggregator integration"""
        try:
            from dex.shared.price_aggregator import EVMPriceAggregator
            
            aggregator = EVMPriceAggregator()
            
            # Test basic functionality
            stats = aggregator.get_cache_stats()
            if not isinstance(stats, dict):
                return {"success": False, "error": "Price aggregator stats not dict"}
            
            # Test cache operations
            aggregator.clear_cache()
            
            # Test chain registration (mock)
            class MockEngine:
                def __init__(self):
                    self.cross_arbitrage = None
            
            mock_engine = MockEngine()
            aggregator.register_chain_engine("test_chain", mock_engine)
            
            if "test_chain" not in aggregator.chain_engines:
                return {"success": False, "error": "Chain registration failed"}
            
            return {"success": True, "message": "Price aggregator working"}
            
        except Exception as e:
            return {"success": False, "error": f"Price aggregator test failed: {e}"}
    
    async def test_cross_chain_compatibility(self) -> Dict[str, Any]:
        """Test cross-chain method compatibility"""
        try:
            from dex.ethereum_service.engine import EthereumEngine
            from dex.bsc_service.engine import BSCEngine
            from dex.polygon_service.engine import PolygonEngine
            from dex.ethereum_service.config import EthereumConfig
            from dex.bsc_service.config import BSCConfig
            from dex.polygon_service.config import PolygonConfig
            
            # Test engine method signatures
            engines = {
                "ethereum": EthereumEngine(EthereumConfig()),
                "bsc": BSCEngine(BSCConfig()),
                "polygon": PolygonEngine(PolygonConfig())
            }
            
            # Check required methods exist
            required_methods = [
                "initialize", "get_balance", "get_gas_price", 
                "execute_transaction", "call_contract", 
                "build_transaction", "wait_for_transaction"
            ]
            
            for chain, engine in engines.items():
                for method in required_methods:
                    if not hasattr(engine, method):
                        return {"success": False, "error": f"{chain} engine missing {method}"}
            
            return {"success": True, "message": "Cross-chain compatibility verified"}
            
        except Exception as e:
            return {"success": False, "error": f"Cross-chain test failed: {e}"}
    
    async def test_engine_methods(self) -> Dict[str, Any]:
        """Test engine method signatures and compatibility"""
        try:
            from dex.bsc_service.engine import BSCEngine
            from dex.polygon_service.engine import PolygonEngine
            from dex.bsc_service.config import BSCConfig
            from dex.polygon_service.config import PolygonConfig
            
            # Test method signatures
            bsc_engine = BSCEngine(BSCConfig())
            polygon_engine = PolygonEngine(PolygonConfig())
            
            # Test call_contract method exists and has correct signature
            import inspect
            
            for engine_name, engine in [("BSC", bsc_engine), ("Polygon", polygon_engine)]:
                if not hasattr(engine, 'call_contract'):
                    return {"success": False, "error": f"{engine_name} missing call_contract method"}
                
                sig = inspect.signature(engine.call_contract)
                expected_params = ['contract_address', 'function_name', 'params']
                actual_params = list(sig.parameters.keys())  # Instance methods don't include 'self'
                
                if actual_params != expected_params:
                    return {"success": False, "error": f"{engine_name} call_contract signature mismatch: expected {expected_params}, got {actual_params}"}
            
            return {"success": True, "message": "Engine methods compatible"}
            
        except Exception as e:
            return {"success": False, "error": f"Engine method test failed: {e}"}
    
    async def test_configuration_consistency(self) -> Dict[str, Any]:
        """Test configuration consistency across services"""
        try:
            from dex.solana_service.config import SolanaConfig
            from dex.ethereum_service.config import EthereumConfig
            from dex.bsc_service.config import BSCConfig
            from dex.polygon_service.config import PolygonConfig
            
            configs = {
                "solana": SolanaConfig(),
                "ethereum": EthereumConfig(),
                "bsc": BSCConfig(),
                "polygon": PolygonConfig()
            }
            
            # Check common configuration patterns
            for chain, config in configs.items():
                # All should have RPC_URL
                if not hasattr(config, 'RPC_URL'):
                    return {"success": False, "error": f"{chain} missing RPC_URL"}
                
                # EVM chains should have similar structure
                if chain in ["ethereum", "bsc", "polygon"]:
                    evm_attrs = ["CHAIN_ID", "GAS_PRICE_MULTIPLIER"]
                    for attr in evm_attrs:
                        if not hasattr(config, attr):
                            return {"success": False, "error": f"{chain} missing {attr}"}
            
            return {"success": True, "message": "Configuration consistency verified"}
            
        except Exception as e:
            return {"success": False, "error": f"Configuration test failed: {e}"}
    
    def print_summary(self):
        """Print test summary"""
        logger.info("\n" + "="*60)
        logger.info("🧪 INTEGRATION QUALITY TEST SUMMARY")
        logger.info("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result["success"])
        failed_tests = total_tests - passed_tests
        
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"✅ Passed: {passed_tests}")
        logger.info(f"❌ Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            logger.info("\n❌ FAILED TESTS:")
            for test_name, result in self.test_results.items():
                if not result["success"]:
                    logger.info(f"  • {test_name}: {result.get('error', 'Unknown error')}")
        
        logger.info("\n📊 DETAILED RESULTS:")
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            logger.info(f"  {test_name}: {status}")
            if result["success"] and "message" in result:
                logger.info(f"    {result['message']}")
        
        logger.info("="*60)
        
        if failed_tests == 0:
            logger.info("🎉 ALL INTEGRATION TESTS PASSED!")
            logger.info("✅ ArbitrageWise services are properly integrated")
        else:
            logger.info("⚠️  INTEGRATION ISSUES DETECTED")
            logger.info("🔧 Please fix the failed tests before production deployment")

async def main():
    """Run integration tests"""
    tester = IntegrationTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
