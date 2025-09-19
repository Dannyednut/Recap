"""
Network-aware contract addresses for all supported chains
Automatically switches between mainnet and testnet based on MAINNET environment variable
"""
import os
from typing import Dict, Any, Optional
from .network_config import NetworkConfig

def get_contract_addresses() -> Dict[str, Dict[str, Any]]:
    """Get contract addresses for all chains based on network configuration"""
    is_mainnet = NetworkConfig.is_mainnet()
    
    addresses = {
        'ethereum': _get_ethereum_addresses(is_mainnet),
        'bsc': _get_bsc_addresses(is_mainnet),
        'polygon': _get_polygon_addresses(is_mainnet)
    }
    
    return addresses

def _get_ethereum_addresses(is_mainnet: bool) -> Dict[str, Any]:
    """Get Ethereum contract addresses"""
    if is_mainnet:
        return {
            'chain_id': 1,
            'network_name': 'mainnet',
            'explorer_api': 'https://api.etherscan.io/api',
            'routers': {
                'uniswap_v2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'sushiswap_v2': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',
                'sushiswap_v3': '0x2214A42d8e2A1d20635c2cb0664422c528B6A432'
            },
            'factories': {
                'uniswap_v2': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                'uniswap_v3': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'sushiswap_v2': '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac'
            },
            'quoters': {
                'uniswap_v3': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
            },
            'tokens': {
                'WETH': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
                'USDC': '0xA0b86a33E6441b8435b662303b1c2B6a6b2b9a6e',
                'USDT': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
                'DAI': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
                'WBTC': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'
            },
            'flash_loan_providers': {
                'aave_v3': '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2',
                'balancer': '0xBA12222222228d8Ba445958a75a0704d566BF2C8'
            }
        }
    else:  # Sepolia testnet
        return {
            'chain_id': 11155111,
            'network_name': 'sepolia',
            'explorer_api': 'https://api-sepolia.etherscan.io/api',
            'routers': {
                'uniswap_v2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'sushiswap_v2': '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506'
            },
            'factories': {
                'uniswap_v2': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                'uniswap_v3': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'sushiswap_v2': '0xc35DADB65012eC5796536bD9864eD8773aBc74C4'
            },
            'quoters': {
                'uniswap_v3': '0xEd1f6473345F45b75F8179591dd5bA1888cf2FB3'
            },
            'tokens': {
                'WETH': '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14',
                'USDC': '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238',
                'USDT': '0x7169D38820dfd117C3FA1f22a697dBA58d90BA06',
                'DAI': '0x3e622317f8C93f7328350cF0B56d9eD4C620C5d6'
            },
            'flash_loan_providers': {
                'aave_v3': '0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951'
            }
        }

def _get_bsc_addresses(is_mainnet: bool) -> Dict[str, Any]:
    """Get BSC contract addresses"""
    if is_mainnet:
        return {
            'chain_id': 56,
            'network_name': 'mainnet',
            'explorer_api': 'https://api.bscscan.com/api',
            'routers': {
                'pancakeswap_v2': '0x10ED43C718714eb63d5aA57B78B54704E256024E',
                'pancakeswap_v3': '0x13f4EA83D0bd40E75C8222255bc855a974568Dd4',
                'biswap': '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8',
                'apeswap': '0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7',
                'bakeryswap': '0xCDe540d7eAFE93aC5fE6233Bee57E1270D3E330F'
            },
            'factories': {
                'pancakeswap_v2': '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73',
                'pancakeswap_v3': '0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865',
                'biswap': '0x858E3312ed3A876947EA49d572A7C42DE08af7EE',
                'apeswap': '0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6',
                'bakeryswap': '0x01bF7C66c6BD861915CdaaE475042d3c4BaE16A7'
            },
            'quoters': {
                'pancakeswap_v3': '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997'
            },
            'tokens': {
                'WBNB': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
                'BUSD': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
                'USDT': '0x55d398326f99059fF775485246999027B3197955',
                'USDC': '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
                'ETH': '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
                'BTCB': '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',
                'CAKE': '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82'
            },
            'flash_loan_providers': {
                'venus': '0xfD36E2c2a6789Db23113685031d7F16329158384'
            }
        }
    else:  # BSC Testnet
        return {
            'chain_id': 97,
            'network_name': 'testnet',
            'explorer_api': 'https://api-testnet.bscscan.com/api',
            'routers': {
                'pancakeswap_v2': '0xD99D1c33F9fC3444f8101754aBC46c52416550D1',
                'pancakeswap_v3': '0x9a489505a00cE272eAa5e07Dba6491314CaE3796',
                'biswap': '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8'
            },
            'factories': {
                'pancakeswap_v2': '0x6725F303b657a9451d8BA641348b6761A6CC7a17',
                'pancakeswap_v3': '0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865',
                'biswap': '0x858E3312ed3A876947EA49d572A7C42DE08af7EE'
            },
            'quoters': {
                'pancakeswap_v3': '0xbC203d7f83677c7ed3F7acEc959963E7F4ECC5C2'
            },
            'tokens': {
                'WBNB': '0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd',
                'BUSD': '0x78867BbEeF44f2326bF8DDd1941a4439382EF2A7',
                'USDT': '0x7ef95a0FEE0Dd31b22626fA2e10Ee6A223F8a684',
                'USDC': '0x64544969ed7EBf5f083679233325356EbE738930',
                'CAKE': '0xFa60D973F7642B748046464e165A65B7323b0DEE'
            },
            'flash_loan_providers': {
                'venus': '0x94c1495cD4c557f1560Cbd68EAB0d197e6291571'
            }
        }

def _get_polygon_addresses(is_mainnet: bool) -> Dict[str, Any]:
    """Get Polygon contract addresses"""
    if is_mainnet:
        return {
            'chain_id': 137,
            'network_name': 'mainnet',
            'explorer_api': 'https://api.polygonscan.com/api',
            'routers': {
                'quickswap_v2': '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',
                'quickswap_v3': '0xf5b509bB0909a69B1c207E495f687a596C168E12',
                'sushiswap_v2': '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
                'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564'
            },
            'factories': {
                'quickswap_v2': '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32',
                'quickswap_v3': '0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28',
                'sushiswap_v2': '0xc35DADB65012eC5796536bD9864eD8773aBc74C4',
                'uniswap_v3': '0x1F98431c8aD98523631AE4a59f267346ea31F984'
            },
            'quoters': {
                'quickswap_v3': '0xa15F0D7377B2A0C0c10262E4ABB447682B47bc88',
                'uniswap_v3': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
            },
            'tokens': {
                'WMATIC': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',
                'USDC': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
                'USDT': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
                'DAI': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063',
                'WETH': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',
                'WBTC': '0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6'
            },
            'flash_loan_providers': {
                'aave_v3': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
                'balancer': '0xBA12222222228d8Ba445958a75a0704d566BF2C8'
            },
            'curve_pools': {
                'aave': '0x445FE580eF8d70FF569aB36e80c647af338db351',
                'ren': '0xC2d95EEF97Ec6C17551d45e77B590dc1F9117C67',
                'am3crv': '0x19793B454D3AfC7b454F206Ffe95aDE26cA6912c'
            }
        }
    else:  # Mumbai testnet
        return {
            'chain_id': 80001,
            'network_name': 'mumbai',
            'explorer_api': 'https://api-testnet.polygonscan.com/api',
            'routers': {
                'quickswap_v2': '0x8954AfA98594b838bda56FE4C12a09D7739D179b',
                'sushiswap_v2': '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
                'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564'
            },
            'factories': {
                'quickswap_v2': '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32',
                'sushiswap_v2': '0xc35DADB65012eC5796536bD9864eD8773aBc74C4',
                'uniswap_v3': '0x1F98431c8aD98523631AE4a59f267346ea31F984'
            },
            'quoters': {
                'uniswap_v3': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
            },
            'tokens': {
                'WMATIC': '0x9c3C9283D3e44854697Cd22D3Faa240Cfb032889',
                'USDC': '0xe11A86849d99F524cAC3E7A0Ec1241828e332C62',
                'USDT': '0xA02f6adc7926efeBBd59Fd43A84f4E0c0c91e832',
                'DAI': '0x001B3B4d0F3714Ca98ba10F6042DaEbF0B1B7b6F',
                'WETH': '0xa6fa4fb5f76172d178d61b04b0ecd319c5d1c0aa'
            },
            'flash_loan_providers': {
                'aave_v3': '0x6C9fB0D5bD9429eb9Cd96B85B81d872281771E6B'
            }
        }

def get_chain_addresses(chain: str) -> Dict[str, Any]:
    """Get addresses for a specific chain"""
    addresses = get_contract_addresses()
    return addresses.get(chain, {})

def get_router_address(chain: str, router_name: str) -> Optional[str]:
    """Get router address for specific chain and router"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('routers', {}).get(router_name)

def get_factory_address(chain: str, factory_name: str) -> Optional[str]:
    """Get factory address for specific chain and factory"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('factories', {}).get(factory_name)

def get_token_address(chain: str, token_symbol: str) -> Optional[str]:
    """Get token address for specific chain and token symbol"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('tokens', {}).get(token_symbol)

def get_base_tokens(chain: str) -> Dict[str, str]:
    """Get base tokens for a specific chain"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('tokens', {})

def get_explorer_api_url(chain: str) -> Optional[str]:
    """Get explorer API URL for a specific chain"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('explorer_api')

def get_network_name(chain: str) -> Optional[str]:
    """Get network name for a specific chain"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('network_name')

def get_chain_id(chain: str) -> Optional[int]:
    """Get chain ID for a specific chain"""
    chain_addresses = get_chain_addresses(chain)
    return chain_addresses.get('chain_id')
