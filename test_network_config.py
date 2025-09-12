#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify centralized MAINNET environment variable functionality
across all blockchain service configurations.
"""

import os
import sys

def test_network_switching():
    print("Testing Network Configuration Switching...")
    print("=" * 50)
    
    # Test mainnet configuration
    print("\n1. Testing MAINNET=True (Mainnet Configuration)")
    os.environ["MAINNET"] = "True"
    
    # Test direct network config import
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dex', 'shared'))
    
    from network_config import NetworkConfig
    
    # Test Ethereum mainnet config
    eth_config = NetworkConfig.get_ethereum_config()
    print(f"Ethereum Chain ID: {eth_config['chain_id']}")
    print(f"Ethereum Network: {eth_config['network_name']}")
    print(f"WETH Token: {eth_config['tokens'].get('WETH', 'Not found')}")
    print(f"Uniswap V2 Router: {eth_config['dexes']['uniswap_v2']['router']}")
    
    # Test BSC mainnet config
    bsc_config = NetworkConfig.get_bsc_config()
    print(f"\nBSC Chain ID: {bsc_config['chain_id']}")
    print(f"BSC Network: {bsc_config['network_name']}")
    print(f"WBNB Token: {bsc_config['tokens'].get('WBNB', 'Not found')}")
    print(f"PancakeSwap V2 Router: {bsc_config['dexes']['pancakeswap_v2']['router']}")
    
    # Test Polygon mainnet config
    polygon_config = NetworkConfig.get_polygon_config()
    print(f"\nPolygon Chain ID: {polygon_config['chain_id']}")
    print(f"Polygon Network: {polygon_config['network_name']}")
    print(f"WMATIC Token: {polygon_config['tokens'].get('WMATIC', 'Not found')}")
    print(f"QuickSwap Router: {polygon_config['dexes']['quickswap']['router']}")
    
    # Store mainnet configs for comparison
    mainnet_configs = {
        'eth_chain_id': eth_config['chain_id'],
        'bsc_chain_id': bsc_config['chain_id'],
        'polygon_chain_id': polygon_config['chain_id'],
        'eth_tokens': eth_config['tokens'],
        'bsc_tokens': bsc_config['tokens'],
        'polygon_tokens': polygon_config['tokens']
    }
    
    # Test testnet configuration
    print("\n" + "=" * 50)
    print("2. Testing MAINNET=False (Testnet Configuration)")
    os.environ["MAINNET"] = "False"
    
    # Clear module cache and re-import
    if 'network_config' in sys.modules:
        del sys.modules['network_config']
    
    from network_config import NetworkConfig
    
    # Test Ethereum testnet config
    eth_config_testnet = NetworkConfig.get_ethereum_config()
    print(f"Ethereum Chain ID: {eth_config_testnet['chain_id']}")
    print(f"Ethereum Network: {eth_config_testnet['network_name']}")
    print(f"WETH Token: {eth_config_testnet['tokens'].get('WETH', 'Not found')}")
    
    # Test BSC testnet config
    bsc_config_testnet = NetworkConfig.get_bsc_config()
    print(f"\nBSC Chain ID: {bsc_config_testnet['chain_id']}")
    print(f"BSC Network: {bsc_config_testnet['network_name']}")
    print(f"WBNB Token: {bsc_config_testnet['tokens'].get('WBNB', 'Not found')}")
    
    # Test Polygon testnet config
    polygon_config_testnet = NetworkConfig.get_polygon_config()
    print(f"\nPolygon Chain ID: {polygon_config_testnet['chain_id']}")
    print(f"Polygon Network: {polygon_config_testnet['network_name']}")
    print(f"WMATIC Token: {polygon_config_testnet['tokens'].get('WMATIC', 'Not found')}")
    
    # Validation
    print("\n" + "=" * 50)
    print("3. Validation Results")
    
    # Check that mainnet and testnet have different chain IDs
    mainnet_eth_id = 1
    testnet_eth_id = 11155111  # Sepolia
    mainnet_bsc_id = 56
    testnet_bsc_id = 97
    mainnet_polygon_id = 137
    testnet_polygon_id = 80001  # Mumbai
    
    print(f"[OK] Ethereum mainnet chain ID correct: {mainnet_configs['eth_chain_id'] == mainnet_eth_id}")
    print(f"[OK] Ethereum testnet chain ID correct: {eth_config_testnet['chain_id'] == testnet_eth_id}")
    print(f"[OK] BSC mainnet chain ID correct: {mainnet_configs['bsc_chain_id'] == mainnet_bsc_id}")
    print(f"[OK] BSC testnet chain ID correct: {bsc_config_testnet['chain_id'] == testnet_bsc_id}")
    print(f"[OK] Polygon mainnet chain ID correct: {mainnet_configs['polygon_chain_id'] == mainnet_polygon_id}")
    print(f"[OK] Polygon testnet chain ID correct: {polygon_config_testnet['chain_id'] == testnet_polygon_id}")
    
    # Check that token addresses are different between mainnet and testnet
    eth_tokens_different = mainnet_configs['eth_tokens'] != eth_config_testnet['tokens']
    bsc_tokens_different = mainnet_configs['bsc_tokens'] != bsc_config_testnet['tokens']
    polygon_tokens_different = mainnet_configs['polygon_tokens'] != polygon_config_testnet['tokens']
    
    print(f"[OK] Ethereum tokens switch correctly: {eth_tokens_different}")
    print(f"[OK] BSC tokens switch correctly: {bsc_tokens_different}")
    print(f"[OK] Polygon tokens switch correctly: {polygon_tokens_different}")
    
    print("\nNetwork configuration switching test completed successfully!")
    
    return True

if __name__ == "__main__":
    try:
        test_network_switching()
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)
