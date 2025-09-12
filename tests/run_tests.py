#!/usr/bin/env python3

import unittest
import sys
import os
import argparse

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


def run_tests(test_modules=None, verbose=False):
    """Run the test suite"""
    # Default test modules
    all_test_modules = [
        'test_arbitrage_strategies',
        'test_mempool_monitor',
        'test_token_discovery',
        'test_flashloan_engine',
        'test_contract_executor'
    ]
    
    # Use specified modules or all modules
    modules_to_test = test_modules if test_modules else all_test_modules
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test modules to suite
    for module_name in modules_to_test:
        try:
            # Import the module
            module = __import__(module_name)
            # Add tests from the module
            suite.addTests(loader.loadTestsFromModule(module))
            print(f"Added tests from {module_name}")
        except ImportError as e:
            print(f"Error importing {module_name}: {e}")
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    
    # Return exit code based on test results
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run ArbitrageWise test suite')
    parser.add_argument(
        '-m', '--modules',
        nargs='+',
        help='Specific test modules to run (e.g., test_arbitrage_strategies test_mempool_monitor)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Run tests
    exit_code = run_tests(args.modules, args.verbose)
    
    # Exit with appropriate code
    sys.exit(exit_code)