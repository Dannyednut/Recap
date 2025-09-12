import importlib
import logging
from typing import Dict, Any, Optional, List, Type

# Import base classes
from .shared.base_engine import BaseEngine
from .shared.base_arbitrage import BaseArbitrageStrategy
from .shared.models.chain_models import ChainConfig

logger = logging.getLogger(__name__)

class ChainFactory:
    """Factory for creating chain-specific components"""
    
    # Supported chains and their module paths
    SUPPORTED_CHAINS = {
        "ethereum": "dex.ethereum_service",
        "bsc": "dex.bsc_service",
        "polygon": "dex.polygon_service",
        "solana": "dex.solana_service",
        # Add more chains as needed
    }
    
    @classmethod
    def create_engine(cls, chain_id: str, config: Dict[str, Any]) -> Optional[BaseEngine]:
        """Create a chain-specific engine"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            module = importlib.import_module(f"{module_path}.engine")
            
            # Get the engine class
            engine_class_name = f"{chain_id.capitalize()}Engine"
            engine_class = getattr(module, engine_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return engine instance
            engine = engine_class(chain_config)
            return engine
            
        except Exception as e:
            logger.error(f"Error creating engine for chain {chain_id}: {e}")
            return None
    
    @classmethod
    def create_arbitrage_strategy(cls, 
                                 chain_id: str, 
                                 strategy_type: str, 
                                 engine: BaseEngine, 
                                 config: Dict[str, Any]) -> Optional[BaseArbitrageStrategy]:
        """Create a chain-specific arbitrage strategy"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            
            # Determine the strategy module based on type
            if strategy_type == "cross":
                strategy_module = f"{module_path}.cross_arbitrage"
            elif strategy_type == "triangular":
                strategy_module = f"{module_path}.triangular_arbitrage"
            else:
                logger.error(f"Unsupported strategy type: {strategy_type}")
                return None
            
            # Import the strategy module
            module = importlib.import_module(strategy_module)
            
            # Get the strategy class
            strategy_class_name = f"{chain_id.capitalize()}{strategy_type.capitalize()}Arbitrage"
            strategy_class = getattr(module, strategy_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return strategy instance
            strategy = strategy_class(engine, chain_config)
            return strategy
            
        except Exception as e:
            logger.error(f"Error creating {strategy_type} strategy for chain {chain_id}: {e}")
            return None
    
    @classmethod
    def create_mempool_monitor(cls, 
                              chain_id: str, 
                              engine: BaseEngine, 
                              config: Dict[str, Any]) -> Optional[Any]:
        """Create a chain-specific mempool monitor"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            module = importlib.import_module(f"{module_path}.mempool_monitor")
            
            # Get the monitor class
            monitor_class_name = f"{chain_id.capitalize()}MempoolMonitor"
            monitor_class = getattr(module, monitor_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return monitor instance
            monitor = monitor_class(engine, chain_config)
            return monitor
            
        except Exception as e:
            logger.error(f"Error creating mempool monitor for chain {chain_id}: {e}")
            return None
    
    @classmethod
    def create_flashloan_engine(cls, 
                               chain_id: str, 
                               engine: BaseEngine, 
                               config: Dict[str, Any]) -> Optional[Any]:
        """Create a chain-specific flashloan engine"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            module = importlib.import_module(f"{module_path}.flashloan_engine")
            
            # Get the flashloan engine class
            flashloan_class_name = f"{chain_id.capitalize()}FlashLoanEngine"
            flashloan_class = getattr(module, flashloan_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return flashloan engine instance
            flashloan_engine = flashloan_class(engine, chain_config)
            return flashloan_engine
            
        except Exception as e:
            logger.error(f"Error creating flashloan engine for chain {chain_id}: {e}")
            return None
    
    @classmethod
    def create_contract_executor(cls, 
                                chain_id: str, 
                                engine: BaseEngine, 
                                config: Dict[str, Any]) -> Optional[Any]:
        """Create a chain-specific contract executor"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            module = importlib.import_module(f"{module_path}.contract_executor")
            
            # Get the contract executor class
            executor_class_name = f"{chain_id.capitalize()}ContractExecutor"
            executor_class = getattr(module, executor_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return contract executor instance
            executor = executor_class(engine, chain_config)
            return executor
            
        except Exception as e:
            logger.error(f"Error creating contract executor for chain {chain_id}: {e}")
            return None
    
    @classmethod
    def create_token_discovery(cls, 
                              chain_id: str, 
                              engine: BaseEngine, 
                              config: Dict[str, Any]) -> Optional[Any]:
        """Create a chain-specific token discovery service"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            module = importlib.import_module(f"{module_path}.token_discovery")
            
            # Get the token discovery class
            discovery_class_name = f"{chain_id.capitalize()}TokenDiscoveryService"
            discovery_class = getattr(module, discovery_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return token discovery instance
            discovery = discovery_class(engine, chain_config)
            return discovery
            
        except Exception as e:
            logger.error(f"Error creating token discovery for chain {chain_id}: {e}")
            return None
    
    @classmethod
    def create_arbitrage_pipeline(cls, 
                                 chain_id: str, 
                                 engine: BaseEngine,
                                 cross_arbitrage: BaseArbitrageStrategy,
                                 triangular_arbitrage: BaseArbitrageStrategy,
                                 mempool_monitor: Any,
                                 flashloan_engine: Any,
                                 contract_executor: Any,
                                 token_discovery: Any,
                                 config: Dict[str, Any]) -> Optional[Any]:
        """Create a chain-specific arbitrage pipeline"""
        try:
            if chain_id not in cls.SUPPORTED_CHAINS:
                logger.error(f"Unsupported chain: {chain_id}")
                return None
            
            # Import the chain-specific module
            module_path = cls.SUPPORTED_CHAINS[chain_id]
            module = importlib.import_module(f"{module_path}.arbitrage_pipeline")
            
            # Get the pipeline class
            pipeline_class_name = f"{chain_id.capitalize()}ArbitragePipeline"
            pipeline_class = getattr(module, pipeline_class_name)
            
            # Create config object
            config_module = importlib.import_module(f"{module_path}.config")
            config_class_name = f"{chain_id.capitalize()}Config"
            config_class = getattr(config_module, config_class_name)
            # Check if config class needs instantiation or is static
            try:
                # Try to instantiate with config parameters
                chain_config = config_class(**config)
            except TypeError:
                # If it fails, use the class directly (static config)
                chain_config = config_class
            
            # Create and return pipeline instance
            pipeline = pipeline_class(
                config=chain_config,
                engine=engine,
                cross_arbitrage=cross_arbitrage,
                triangular_arbitrage=triangular_arbitrage,
                mempool_monitor=mempool_monitor,
                flashloan_engine=flashloan_engine,
                contract_executor=contract_executor,
                token_discovery=token_discovery
            )
            return pipeline
            
        except Exception as e:
            logger.error(f"Error creating arbitrage pipeline for chain {chain_id}: {e}")
            return None