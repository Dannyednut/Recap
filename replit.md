# Overview

This is a comprehensive multi-chain cryptocurrency arbitrage trading system that identifies and executes profitable trading opportunities across centralized exchanges (CEX) and decentralized exchanges (DEX). The system monitors price differences between exchanges and automatically executes trades to capture arbitrage profits using various strategies including cross-exchange arbitrage, triangular arbitrage, and flash loan arbitrage.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Components

**CEX Arbitrage Engine**
- Built with Python using asyncio for concurrent processing
- Uses CCXT library for exchange integration and WebSocket connections for real-time price feeds
- Implements cross-exchange and triangular arbitrage strategies
- Features a Quart-based REST API for trade execution and monitoring

**DEX Arbitrage Engine**
- Multi-chain architecture supporting Ethereum, BSC, Polygon, and Solana
- Each chain has dedicated microservices with shared interfaces and models
- Uses Web3.py for Ethereum-based chains and Solana's Python SDK for Solana operations
- Implements protocol adapters for major DEXes (Uniswap V2/V3, PancakeSwap, QuickSwap, Raydium, etc.)

**Orchestration Layer**
- Central coordinator managing all arbitrage engines across chains
- Opportunity aggregator collecting and filtering profitable trades
- Risk manager implementing position limits and safety checks
- Execution coordinator handling trade routing and gas optimization

## Trading Strategies

**Cross-Exchange Arbitrage**
- Monitors price differences between exchanges for the same trading pair
- Executes simultaneous buy/sell orders to capture price spreads
- Supports both CEX-to-CEX and DEX-to-DEX arbitrage

**Triangular Arbitrage**
- Identifies circular trading opportunities within single exchanges
- Example: ETH → USDC → DAI → ETH for profit
- Uses mathematical calculations to detect profitable trading paths

**Flash Loan Arbitrage**
- Leverages flash loans for capital-free arbitrage execution
- Integrates with Aave, dYdX, and other lending protocols
- Enables large-scale arbitrage without upfront capital requirements

## Configuration Management

**Centralized Network Configuration**
- Single `MAINNET` environment variable controls all blockchain networks
- Automatic switching between mainnet and testnet configurations
- Centralized management of chain IDs, RPC URLs, token addresses, and DEX contracts
- Eliminates configuration drift between blockchain services

**Environment-Based Configuration**
- Uses .env files and environment variables for sensitive data
- Shared configuration classes inheriting from centralized network config
- Validates required parameters on startup with meaningful error messages

**Trading Parameters**
- Configurable profit thresholds, gas limits, and position sizes
- Support for multiple trading pairs and exchange selection
- Risk management parameters including maximum slippage and trade amounts

## Real-Time Monitoring

**WebSocket Price Feeds**
- Maintains persistent connections to exchange WebSocket APIs
- Implements automatic reconnection with exponential backoff
- Caches price data with timestamp tracking for opportunity detection

**Telegram Integration**
- Real-time alerts for detected opportunities
- Interactive buttons for manual trade execution approval
- Whitelisted chat support for security

## Database and Storage

**In-Memory Caching**
- Price cache with TTL for fast opportunity detection
- Account balance tracking with periodic updates
- Trade history and execution metrics storage

**Configuration Storage**
- Dynamic configuration updates via API endpoints
- Supports hot-reloading of trading parameters
- Maintains audit trail of configuration changes

## Error Handling and Resilience

**Robust Error Management**
- Comprehensive exception handling with detailed logging
- Automatic retry mechanisms for failed operations
- Circuit breaker patterns for external service calls

**Health Monitoring**
- Service health checks with status reporting
- Automatic failover and recovery mechanisms
- Performance metrics and execution tracking

# External Dependencies

## Centralized Exchange APIs
- **CCXT Library**: Unified interface for 150+ cryptocurrency exchanges
- **WebSocket Connections**: Real-time price feeds from Binance, OKEx, Bybit, and others
- **Rate Limiting**: Compliance with exchange API limits and authentication

## Blockchain Networks
- **Ethereum**: Web3.py for smart contract interactions, Infura/Alchemy for RPC access
- **BSC**: Binance Smart Chain with PancakeSwap and other DEX integrations
- **Polygon**: Polygon PoS chain with QuickSwap and Uniswap V3 support
- **Solana**: Native Solana RPC client with Jupiter aggregator integration

## DeFi Protocols
- **Uniswap V2/V3**: Automated market maker with concentrated liquidity
- **SushiSwap**: Multi-chain DEX with additional features
- **PancakeSwap**: BSC's leading DEX with V2 and V3 protocols
- **Raydium**: Solana's premier AMM and DEX
- **Flash Loan Providers**: Aave V3, dYdX, Balancer, Mango V4

## Communication Services
- **Telegram Bot API**: Alert system with interactive trade execution
- **Aiogram**: Async Telegram bot framework for Python
- **WebSocket Libraries**: Real-time communication for price feeds

## Development and Deployment
- **Quart Framework**: Async web framework for REST API endpoints
- **Uvicorn**: ASGI server for production deployment
- **Python-dotenv**: Environment variable management
- **Structlog**: Structured logging for debugging and monitoring

## Mathematical Libraries
- **SciPy**: Scientific computing for advanced arbitrage calculations
- **Decimal**: High-precision decimal arithmetic for financial calculations
- **Asyncio**: Concurrent programming for real-time trading operations