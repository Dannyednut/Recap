"""
Flashbots Relay Integration for MEV-Protected Transaction Submission
Handles bundle creation, signing, and submission to Flashbots relay
"""

import asyncio
import json
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3
from web3.types import TxParams
import aiohttp
import time

logger = logging.getLogger(__name__)

@dataclass
class FlashbotsBundle:
    """Represents a Flashbots bundle with transactions and metadata"""
    transactions: List[str]  # List of signed transaction hex strings
    block_number: int        # Target block number
    min_timestamp: Optional[int] = None
    max_timestamp: Optional[int] = None
    reverting_tx_hashes: Optional[List[str]] = None

@dataclass
class BundleStats:
    """Bundle simulation and inclusion statistics"""
    bundle_hash: str
    simulation_success: bool
    coinbase_diff: int
    eth_sent_to_coinbase: int
    gas_fees: int
    gas_used: int
    gas_price: int

class FlashbotsRelay:
    """
    Flashbots Relay client for submitting MEV bundles
    Supports both mainnet and testnet (Goerli) Flashbots relays
    """
    
    MAINNET_RELAY_URL = "https://relay.flashbots.net"
    GOERLI_RELAY_URL = "https://relay-goerli.flashbots.net"
    
    def __init__(self, w3: AsyncWeb3, private_key: str, relay_url: Optional[str] = None):
        """
        Initialize Flashbots relay client
        
        Args:
            w3: AsyncWeb3 instance
            private_key: Private key for signing bundles
            relay_url: Custom relay URL (defaults to mainnet)
        """
        self.w3 = w3
        self.account: LocalAccount = Account.from_key(private_key)
        self.relay_url = relay_url or self.MAINNET_RELAY_URL
        
        # Generate Flashbots identity for authentication
        self.flashbots_signer = Account.create()
        
        logger.info(f"Initialized Flashbots relay client for {self.relay_url}")
        logger.info(f"Flashbots identity: {self.flashbots_signer.address}")
    
    async def send_bundle(self, bundle: FlashbotsBundle) -> Dict[str, Any]:
        """
        Send bundle to Flashbots relay
        
        Args:
            bundle: FlashbotsBundle to submit
            
        Returns:
            Response from Flashbots relay
        """
        try:
            # Prepare bundle payload
            payload = {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "eth_sendBundle",
                "params": [
                    {
                        "txs": bundle.transactions,
                        "blockNumber": hex(bundle.block_number),
                        "minTimestamp": bundle.min_timestamp,
                        "maxTimestamp": bundle.max_timestamp,
                        "revertingTxHashes": bundle.reverting_tx_hashes or []
                    }
                ]
            }
            
            # Sign the request
            headers = await self._get_signed_headers(payload)
            
            # Submit to relay
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.relay_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        logger.info(f"Bundle submitted successfully: {result}")
                        return result
                    else:
                        logger.error(f"Bundle submission failed: {result}")
                        raise Exception(f"Flashbots submission failed: {result}")
                        
        except Exception as e:
            logger.error(f"Error submitting bundle to Flashbots: {e}")
            raise
    
    async def simulate_bundle(self, bundle: FlashbotsBundle) -> BundleStats:
        """
        Simulate bundle execution before submission
        
        Args:
            bundle: FlashbotsBundle to simulate
            
        Returns:
            BundleStats with simulation results
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "eth_callBundle",
                "params": [
                    {
                        "txs": bundle.transactions,
                        "blockNumber": hex(bundle.block_number),
                        "stateBlockNumber": "latest"
                    }
                ]
            }
            
            headers = await self._get_signed_headers(payload)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.relay_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200 and "result" in result:
                        sim_result = result["result"]
                        return BundleStats(
                            bundle_hash=sim_result.get("bundleHash", ""),
                            simulation_success=True,
                            coinbase_diff=int(sim_result.get("coinbaseDiff", "0"), 16),
                            eth_sent_to_coinbase=int(sim_result.get("ethSentToCoinbase", "0"), 16),
                            gas_fees=int(sim_result.get("gasFees", "0"), 16),
                            gas_used=int(sim_result.get("gasUsed", "0"), 16),
                            gas_price=int(sim_result.get("gasPrice", "0"), 16)
                        )
                    else:
                        logger.error(f"Bundle simulation failed: {result}")
                        return BundleStats(
                            bundle_hash="",
                            simulation_success=False,
                            coinbase_diff=0,
                            eth_sent_to_coinbase=0,
                            gas_fees=0,
                            gas_used=0,
                            gas_price=0
                        )
                        
        except Exception as e:
            logger.error(f"Error simulating bundle: {e}")
            raise
    
    async def get_bundle_stats(self, bundle_hash: str, block_number: int) -> Optional[Dict[str, Any]]:
        """
        Get bundle inclusion statistics
        
        Args:
            bundle_hash: Hash of the submitted bundle
            block_number: Block number where bundle was targeted
            
        Returns:
            Bundle statistics or None if not found
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "flashbots_getBundleStats",
                "params": [
                    {
                        "bundleHash": bundle_hash,
                        "blockNumber": hex(block_number)
                    }
                ]
            }
            
            headers = await self._get_signed_headers(payload)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.relay_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200 and "result" in result:
                        return result["result"]
                    else:
                        logger.warning(f"Bundle stats not found: {result}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting bundle stats: {e}")
            return None
    
    async def create_backrun_bundle(
        self,
        target_tx_hash: str,
        backrun_tx: TxParams,
        target_block: int,
        max_priority_fee: int = 2 * 10**9,  # 2 gwei
        tip_percentage: float = 0.1  # 10% tip to miner
    ) -> FlashbotsBundle:
        """
        Create a backrun bundle with target transaction and backrun transaction
        
        Args:
            target_tx_hash: Hash of transaction to backrun
            backrun_tx: Backrun transaction parameters
            target_block: Target block number
            max_priority_fee: Maximum priority fee per gas
            tip_percentage: Percentage of profit to tip miner
            
        Returns:
            FlashbotsBundle ready for submission
        """
        try:
            # Get target transaction
            target_tx = await self.w3.eth.get_transaction(target_tx_hash)
            if not target_tx:
                raise ValueError(f"Target transaction not found: {target_tx_hash}")
            
            # Calculate competitive gas price
            base_fee = await self._get_base_fee(target_block)
            target_gas_price = target_tx.get('gasPrice', 0)
            target_max_fee = target_tx.get('maxFeePerGas', 0)
            
            # Set backrun transaction gas to be slightly higher than target
            if target_max_fee > 0:
                # EIP-1559 transaction
                backrun_tx['maxFeePerGas'] = min(target_max_fee + 1 * 10**9, base_fee + max_priority_fee)
                backrun_tx['maxPriorityFeePerGas'] = min(max_priority_fee, backrun_tx['maxFeePerGas'] - base_fee)
            else:
                # Legacy transaction
                backrun_tx['gasPrice'] = target_gas_price + 1 * 10**9
            
            # Set nonce
            backrun_tx['nonce'] = await self.w3.eth.get_transaction_count(self.account.address)
            
            # Sign backrun transaction
            signed_backrun = self.account.sign_transaction(backrun_tx)
            
            # Create bundle with target tx first, then backrun
            bundle = FlashbotsBundle(
                transactions=[
                    target_tx_hash,  # Include target transaction by hash
                    signed_backrun.rawTransaction.hex()
                ],
                block_number=target_block,
                min_timestamp=int(time.time()),
                max_timestamp=int(time.time()) + 120  # 2 minute window
            )
            
            logger.info(f"Created backrun bundle for block {target_block}")
            return bundle
            
        except Exception as e:
            logger.error(f"Error creating backrun bundle: {e}")
            raise
    
    async def create_arbitrage_bundle(
        self,
        arbitrage_txs: List[TxParams],
        target_block: int,
        miner_tip: int = 0
    ) -> FlashbotsBundle:
        """
        Create arbitrage bundle with multiple transactions
        
        Args:
            arbitrage_txs: List of arbitrage transaction parameters
            target_block: Target block number
            miner_tip: Additional tip to miner in wei
            
        Returns:
            FlashbotsBundle ready for submission
        """
        try:
            signed_txs = []
            nonce = await self.w3.eth.get_transaction_count(self.account.address)
            
            for i, tx in enumerate(arbitrage_txs):
                tx['nonce'] = nonce + i
                signed_tx = self.account.sign_transaction(tx)
                signed_txs.append(signed_tx.rawTransaction.hex())
            
            # Add miner tip transaction if specified
            if miner_tip > 0:
                tip_tx = {
                    'to': '0x0000000000000000000000000000000000000000',  # Burn address
                    'value': miner_tip,
                    'gas': 21000,
                    'gasPrice': await self.w3.eth.gas_price,
                    'nonce': nonce + len(arbitrage_txs)
                }
                signed_tip = self.account.sign_transaction(tip_tx)
                signed_txs.append(signed_tip.rawTransaction.hex())
            
            bundle = FlashbotsBundle(
                transactions=signed_txs,
                block_number=target_block,
                min_timestamp=int(time.time()),
                max_timestamp=int(time.time()) + 60
            )
            
            logger.info(f"Created arbitrage bundle with {len(signed_txs)} transactions")
            return bundle
            
        except Exception as e:
            logger.error(f"Error creating arbitrage bundle: {e}")
            raise
    
    async def _build_backrun_transaction(self, arbitrage_params: Dict[str, Any]) -> Dict[str, Any]:
        """Build backrun transaction without sending to mempool"""
        # This method should be implemented by the contract executor
        # For now, return the params as transaction data
        return {
            'to': arbitrage_params.get('contractAddress'),
            'data': arbitrage_params.get('calldata', '0x'),
            'gas': arbitrage_params.get('gasLimit', 600000),
            'gasPrice': arbitrage_params.get('gasPrice', 0),
            'maxFeePerGas': arbitrage_params.get('maxGasPrice', 0),
            'maxPriorityFeePerGas': arbitrage_params.get('priorityFee', 2000000000),
            'value': arbitrage_params.get('value', 0)
        }
    
    async def _get_signed_headers(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Generate signed headers for Flashbots authentication"""
        message = json.dumps(payload, separators=(',', ':'))
        signature = self.flashbots_signer.sign_message_hash(
            self.w3.keccak(text=message)
        )
        
        return {
            'Content-Type': 'application/json',
            'X-Flashbots-Signature': f"{self.flashbots_signer.address}:{signature.signature.hex()}"
        }
    
    async def _get_base_fee(self, block_number: int) -> int:
        """Get base fee for target block"""
        try:
            if block_number == 0:
                block = await self.w3.eth.get_block('latest')
            else:
                block = await self.w3.eth.get_block(block_number)
            
            return block.get('baseFeePerGas', 0)
        except Exception:
            # Fallback to current base fee
            latest_block = await self.w3.eth.get_block('latest')
            return latest_block.get('baseFeePerGas', 0)

class FlashbotsIntegration:
    """
    High-level Flashbots integration for ArbitrageWise
    Manages bundle creation, submission, and monitoring
    """
    
    def __init__(self, w3: AsyncWeb3, private_key: str, relay_url: Optional[str] = None):
        self.relay = FlashbotsRelay(w3, private_key, relay_url)
        self.w3 = w3
        
    async def submit_backrun_arbitrage(
        self,
        target_tx_hash: str,
        arbitrage_params: Dict[str, Any],
        contract_executor
    ) -> Optional[str]:
        """
        Submit backrun arbitrage via Flashbots bundle
        
        Args:
            target_tx_hash: Transaction to backrun
            arbitrage_params: Arbitrage parameters
            contract_executor: Contract executor instance
            
        Returns:
            Bundle hash if successful, None otherwise
        """
        try:
            # Get current block number
            current_block = await self.w3.eth.block_number
            target_block = current_block + 1
            
            # Build backrun transaction (without sending)
            backrun_tx = await contract_executor._build_backrun_transaction(arbitrage_params)
            
            # Create bundle
            bundle = await self.relay.create_backrun_bundle(
                target_tx_hash,
                backrun_tx,
                target_block
            )
            
            # Simulate bundle first
            stats = await self.relay.simulate_bundle(bundle)
            if not stats.simulation_success:
                logger.warning("Bundle simulation failed, skipping submission")
                return None
            
            if stats.coinbase_diff <= 0:
                logger.warning("Bundle not profitable, skipping submission")
                return None
            
            # Submit bundle
            result = await self.relay.send_bundle(bundle)
            bundle_hash = result.get('result', {}).get('bundleHash')
            
            logger.info(f"Backrun bundle submitted: {bundle_hash}")
            return bundle_hash
            
        except Exception as e:
            logger.error(f"Error submitting backrun bundle: {e}")
            return None
    
    async def monitor_bundle_inclusion(
        self,
        bundle_hash: str,
        target_block: int,
        timeout: int = 300
    ) -> bool:
        """
        Monitor bundle inclusion in target block
        
        Args:
            bundle_hash: Hash of submitted bundle
            target_block: Target block number
            timeout: Timeout in seconds
            
        Returns:
            True if bundle was included, False otherwise
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                current_block = await self.w3.eth.block_number
                
                if current_block >= target_block:
                    # Check if bundle was included
                    stats = await self.relay.get_bundle_stats(bundle_hash, target_block)
                    if stats:
                        logger.info(f"Bundle included in block {target_block}: {stats}")
                        return True
                    else:
                        logger.warning(f"Bundle not included in block {target_block}")
                        return False
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error monitoring bundle: {e}")
                await asyncio.sleep(1)
        
        logger.warning(f"Bundle monitoring timeout for {bundle_hash}")
        return False
