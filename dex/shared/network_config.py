"""
Centralized network configuration for all blockchain services
Controls mainnet/testnet switching with single MAINNET environment variable
"""
import os
from typing import Dict, Any

# Global network setting - controls all chains
MAINNET = os.getenv("MAINNET", "True").lower() == "true"

class NetworkConfig:
    """Centralized network configuration for all blockchain services"""
    
    @staticmethod
    def get_ethereum_config() -> Dict[str, Any]:
        """Get Ethereum network configuration based on MAINNET setting"""
        if MAINNET:
            return {
                "chain_id": 1,
                "network_name": "ethereum-mainnet",
                "rpc_url": os.getenv("ETH_RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"),
                "ws_url": os.getenv("ETH_WSS_URL", "wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"),
                "explorer_url": "https://etherscan.io",
                "tokens": {
                    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48",
                    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
                    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
                },
                "dexes": {
                    "uniswap_v2": {
                        "factory": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                        "router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
                    },
                    "uniswap_v3": {
                        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                        "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                        "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
                    },
                    "sushiswap": {
                        "factory": "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac",
                        "router": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
                    }
                }
            }
        else:
            return {
                "chain_id": 11155111,  # Sepolia
                "network_name": "ethereum-sepolia",
                "rpc_url": os.getenv("ETH_RPC_URL", "https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY"),
                "ws_url": os.getenv("ETH_WSS_URL", "wss://eth-sepolia.g.alchemy.com/v2/YOUR_KEY"),
                "explorer_url": "https://sepolia.etherscan.io",
                "tokens": {
                    "WETH": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
                    "USDC": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
                    "USDT": "0x7169D38820dfd117C3FA1f22a697dBA58d90BA06",
                    "DAI": "0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357",
                    "WBTC": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063"
                },
                "dexes": {
                    "uniswap_v2": {
                        "factory": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                        "router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
                    },
                    "uniswap_v3": {
                        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                        "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                        "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
                    },
                    "sushiswap": {
                        "factory": "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac",
                        "router": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
                    }
                }
            }
    
    @staticmethod
    def get_bsc_config() -> Dict[str, Any]:
        """Get BSC network configuration based on MAINNET setting"""
        if MAINNET:
            return {
                "chain_id": 56,
                "network_name": "bsc-mainnet",
                "rpc_url": os.getenv("BSC_RPC_URL", "https://bsc-dataseed1.binance.org/"),
                "ws_url": os.getenv("BSC_WSS_URL", "wss://bsc-ws-node.nariox.org:443"),
                "explorer_url": "https://bscscan.com",
                "tokens": {
                    "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
                    "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
                    "USDT": "0x55d398326f99059fF775485246999027B3197955",
                    "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
                    "BTCB": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c"
                },
                "dexes": {
                    "pancakeswap_v2": {
                        "factory": "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73",
                        "router": "0x10ED43C718714eb63d5aA57B78B54704E256024E"
                    },
                    "pancakeswap_v3": {
                        "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
                        "router": "0x1b81D678ffb9C0263b24A97847620C99d213eB14"
                    },
                    "biswap": {
                        "factory": "0x858E3312ed3A876947EA49d572A7C42DE08af7EE",
                        "router": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8"
                    }
                }
            }
        else:
            return {
                "chain_id": 97,  # BSC Testnet
                "network_name": "bsc-testnet",
                "rpc_url": os.getenv("BSC_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545/"),
                "ws_url": os.getenv("BSC_WSS_URL", "wss://bsc-testnet.nodereal.io/ws/v1/YOUR_KEY"),
                "explorer_url": "https://testnet.bscscan.com",
                "tokens": {
                    "WBNB": "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd",
                    "USDC": "0x64544969ed7EBf5f083679233325356EbE738930",
                    "USDT": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
                    "BUSD": "0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee"
                },
                "dexes": {
                    "pancakeswap_v2": {
                        "factory": "0x6725F303b657a9451d8BA641348b6761A6CC7a17",
                        "router": "0xD99D1c33F9fC3444f8101754aBC46c52416550D1"
                    }
                }
            }
    
    @staticmethod
    def get_polygon_config() -> Dict[str, Any]:
        """Get Polygon network configuration based on MAINNET setting"""
        if MAINNET:
            return {
                "chain_id": 137,
                "network_name": "polygon-mainnet",
                "rpc_url": os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com/"),
                "ws_url": os.getenv("POLYGON_WSS_URL", "wss://polygon-rpc.com/"),
                "explorer_url": "https://polygonscan.com",
                "tokens": {
                    "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
                    "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                    "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
                    "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
                    "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6"
                },
                "dexes": {
                    "quickswap": {
                        "factory": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
                        "router": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"
                    },
                    "sushiswap": {
                        "factory": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
                        "router": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
                    },
                    "uniswap_v3": {
                        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                        "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                        "quoter": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
                    }
                }
            }
        else:
            return {
                "chain_id": 80001,  # Mumbai Testnet
                "network_name": "polygon-mumbai",
                "rpc_url": os.getenv("POLYGON_RPC_URL", "https://rpc-mumbai.maticvigil.com/"),
                "ws_url": os.getenv("POLYGON_WSS_URL", "wss://rpc-mumbai.maticvigil.com/ws"),
                "explorer_url": "https://mumbai.polygonscan.com",
                "tokens": {
                    "WMATIC": "0x9c3C9283D3e44854697Cd22D3Faa240Cfb032889",
                    "USDC": "0xe6b8a5CF854791412c1f6EFC7CAf629f5Df1c747",
                    "USDT": "0xA02f6adc7926efeBBd59Fd43A84f4E0c0c91e832",
                    "DAI": "0x001B3B4d0F3714Ca98ba10F6042DaEbF0B1B7b6F"
                },
                "dexes": {
                    "quickswap": {
                        "factory": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
                        "router": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"
                    }
                }
            }
    
    @staticmethod
    def get_solana_config() -> Dict[str, Any]:
        """Get Solana network configuration based on MAINNET setting"""
        if MAINNET:
            return {
                "network": "mainnet-beta",
                "network_name": "solana-mainnet",
                "rpc_url": os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
                "ws_url": os.getenv("SOLANA_WSS_URL", "wss://api.mainnet-beta.solana.com"),
                "explorer_url": "https://explorer.solana.com",
                "tokens": {
                    "WSOL": "So11111111111111111111111111111111111111112",
                    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
                    "SRM": "SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKWRt"
                },
                "dexes": {
                    "raydium": {
                        "program_id": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
                    },
                    "orca": {
                        "program_id": "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP"
                    },
                    "serum": {
                        "program_id": "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
                    }
                }
            }
        else:
            return {
                "network": "devnet",
                "network_name": "solana-devnet",
                "rpc_url": os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com"),
                "ws_url": os.getenv("SOLANA_WSS_URL", "wss://api.devnet.solana.com"),
                "explorer_url": "https://explorer.solana.com?cluster=devnet",
                "tokens": {
                    "WSOL": "So11111111111111111111111111111111111111112",
                    "USDC": "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",  # Devnet USDC
                    "USDT": "EJwZgeZrdC8TXTQbQBoL6bfuAnFUUy1PVCMB4DYPzVaS"   # Devnet USDT
                },
                "dexes": {
                    "raydium": {
                        "program_id": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
                    }
                }
            }
    
    @staticmethod
    def get_all_configs() -> Dict[str, Dict[str, Any]]:
        """Get all network configurations"""
        return {
            "ethereum": NetworkConfig.get_ethereum_config(),
            "bsc": NetworkConfig.get_bsc_config(),
            "polygon": NetworkConfig.get_polygon_config(),
            "solana": NetworkConfig.get_solana_config(),
            "mainnet": MAINNET
        }
    
    @staticmethod
    def is_mainnet() -> bool:
        """Check if running on mainnet"""
        return MAINNET
    
    @staticmethod
    def get_network_type() -> str:
        """Get current network type"""
        return "mainnet" if MAINNET else "testnet"
