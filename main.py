import asyncio
from dataclasses import asdict
from quart import Quart, jsonify, request
from datetime import datetime

# Custom imports
from cex.config import Config
from cex.models import TradeResult
from cex.arbitrage import ArbitrageApp, logger

# DEX imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'dex'))

# Import just the Ethereum service directly (avoiding complex orchestrator imports)
try:
    from ethereum_service.service import EthereumArbitrageService
    from ethereum_service.config import EthereumConfig
    DEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DEX imports failed: {e}")
    DEX_AVAILABLE = False


# --- Quart App and Global App Instance ---
app = Quart(__name__)
arbitrage_app = ArbitrageApp(Config())

# Global DEX service (Ethereum only for now)
ethereum_dex_service = None

# Simple API key auth header name
API_KEY_HEADER = "X-API-KEY"


@app.route('/')
async def index():
    return "Hello there, I'm busy working"


@app.route('/balances', methods=['GET'])
async def get_balances():
    cex_balances = arbitrage_app.engine.account_balances or {}
    
    # Get DEX balances if available
    dex_balances = {}
    if ethereum_dex_service:
        try:
            eth_status = await ethereum_dex_service.get_status()
            dex_balances = {"ethereum": eth_status}
        except Exception as e:
            logger.warning(f"Failed to get DEX balances: {e}")
    
    return jsonify({
        "cex": cex_balances,
        "dex": dex_balances,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/execute', methods=['POST'])
async def execute_trade_endpoint():
    # Require API key header for API-triggered execution
    api_key = request.headers.get(API_KEY_HEADER) or request.args.get('api_key')
    if not api_key:
        return jsonify({"status": "error", "message": "API key required"}), 401
    
    data = await request.get_json()
    if not data or not all(k in data for k in ['opportunity_id', 'type', 'strategy']):
        return jsonify({"status": "error", "message": "Missing required parameters"}), 400

    # Pass the auth key into execute_trade_logic which performs auth validation
    try:
        result = await arbitrage_app.execute_trade_logic(data, auth_key=api_key)
        status_code = 200 if result.status == 'success' else 400

        if 'chat_id' in data and arbitrage_app.notifier:
            await arbitrage_app.notifier.send_trade_result(int(data['chat_id']), result)

        return jsonify(asdict(result)), status_code

    except asyncio.TimeoutError:
        return jsonify({"status": "error", "message": "Trade execution timed out."}), 504
    except Exception as e:
        logger.error(f"API endpoint error: {e}")
        return jsonify({"status": "error", "message": "An internal server error occurred."}), 500


# DISABLED: Insecure telegram webhook - requires signature verification
# @app.route('/telegram-webhook', methods=['POST'])
async def _disabled_telegram_webhook():
    data = await request.get_json()

    if 'callback_query' in data:
        callback = data['callback_query']
        chat_id = callback['message']['chat']['id']
        if str(chat_id) != str(Config.TELEGRAM_CHAT_ID):
            return jsonify(ok=True)  # ignore non-whitelisted chats

        data_str = callback['data']  # expecting format like "exec|instant|opid"
        parts = data_str.split('|')
        if len(parts) != 3:
            return jsonify(ok=True)

        action, subtype, opportunity_id = parts
        if action == "exec":
            exec_payload = {
                "type": "cross" if subtype in ("instant", "transfer") else "triangular",
                "strategy": subtype,
                "opportunity_id": opportunity_id,
                "chat_id": chat_id
            }
            try:
                result = await arbitrage_app.execute_trade_logic(exec_payload, auth_key=Config.BASE44_APP_TOKEN)
                if result.status != "success":
                    logger.error(f"Trade execution from Telegram button failed: {result.message}")
                    result = TradeResult("error", f"Trade execution failed: {result.message}")
            except Exception as e:
                logger.error(f"Error executing trade from Telegram button: {e}")
                result = TradeResult("error", "Failed to execute trade from Telegram button.")

            if arbitrage_app.notifier:
                await arbitrage_app.notifier.send_trade_result(chat_id, result)

    return jsonify(ok=True)


@app.route('/dex/status', methods=['GET'])
async def get_dex_status():
    """Get DEX system status"""
    if not ethereum_dex_service:
        return jsonify({"status": "not_initialized", "available": DEX_AVAILABLE}), 503
    
    try:
        status = await ethereum_dex_service.get_status()
        return jsonify({"ethereum": status, "status": "initialized"})
    except Exception as e:
        logger.error(f"Error getting DEX status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/dex/opportunities', methods=['GET'])
async def get_dex_opportunities():
    """Get DEX arbitrage opportunities"""
    if not ethereum_dex_service:
        return jsonify({"status": "error", "message": "DEX system not initialized"}), 503
    
    try:
        # For now, just return placeholder - the service needs proper opportunity scanning
        opportunities = {"ethereum": "scanning_not_implemented_yet"}
        return jsonify({
            "opportunities": opportunities,
            "chains": ["ethereum"],
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error scanning DEX opportunities: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/system/status', methods=['GET'])
async def get_system_status():
    """Get comprehensive system status"""
    cex_status = {
        "running": True,
        "exchanges": len(arbitrage_app.engine.exchanges),
        "balances_loaded": bool(arbitrage_app.engine.account_balances)
    }
    
    dex_status = {"initialized": False, "available": DEX_AVAILABLE}
    if ethereum_dex_service:
        try:
            eth_status = await ethereum_dex_service.get_status()
            dex_status = {"initialized": True, "ethereum": eth_status}
        except Exception as e:
            dex_status = {"error": str(e)}
    
    return jsonify({
        "cex": cex_status,
        "dex": dex_status,
        "timestamp": datetime.now().isoformat()
    })


# --- Main Entry Point ---
if __name__ == "__main__":

    async def main():
        global ethereum_dex_service
        try:
            # Initialize DEX system (Ethereum only for now)
            if DEX_AVAILABLE:
                logger.info("Initializing Ethereum DEX service...")
                try:
                    ethereum_config = EthereumConfig()
                    ethereum_dex_service = EthereumArbitrageService()
                    await ethereum_dex_service.initialize()
                    logger.info("Ethereum DEX service initialized successfully")
                except Exception as e:
                    logger.warning(f"Ethereum DEX initialization failed (continuing with CEX only): {e}")
                    ethereum_dex_service = None
            
            # Start the CEX scanner tasks
            scanner_task = asyncio.create_task(arbitrage_app.run_scanners())
            
            # Start DEX service if available
            dex_task = None
            if ethereum_dex_service:
                dex_task = asyncio.create_task(ethereum_dex_service.start())
                logger.info("Started Ethereum DEX service")
            
            # Start Quart API server and wait for all services
            if dex_task:
                await asyncio.gather(
                    app.run_task(host=Config.FLASK_HOST, port=Config.FLASK_PORT),
                    scanner_task,
                    dex_task
                )
            else:
                await app.run_task(host=Config.FLASK_HOST, port=Config.FLASK_PORT)
                await scanner_task
        except KeyboardInterrupt:
            logger.info("Shutdown signal received. Exiting.")
        finally:
            # Shutdown both systems
            await arbitrage_app.engine.stop()
            if ethereum_dex_service:
                try:
                    await ethereum_dex_service.stop()
                except Exception as e:
                    logger.warning(f"Error stopping Ethereum DEX service: {e}")
            logger.info("Application shut down gracefully.")

    asyncio.run(main())
