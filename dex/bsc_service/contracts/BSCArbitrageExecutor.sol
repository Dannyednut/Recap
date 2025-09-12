// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

// PancakeSwap V2 interfaces
interface IPancakeRouter {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
    
    function getAmountsOut(uint amountIn, address[] calldata path)
        external view returns (uint[] memory amounts);
}

// PancakeSwap V3 interfaces  
interface IPancakeV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    
    function exactInputSingle(ExactInputSingleParams calldata params)
        external payable returns (uint256 amountOut);
}

// Venus (Aave-like) flash loan interface for BSC
interface IVenusPool {
    function flashLoan(
        address receiverAddress,
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata modes,
        address onBehalfOf,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

contract BSCArbitrageExecutor is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;
    
    // BSC DEX router addresses
    address public constant PANCAKESWAP_V2_ROUTER = 0x10ED43C718714eb63d5aA57B78B54704E256024E;
    address public constant PANCAKESWAP_V3_ROUTER = 0x1b81D678ffb9C0263b24A97847620C99d213eB14;
    address public constant BISWAP_ROUTER = 0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8;
    address public constant APESWAP_ROUTER = 0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7;
    
    // Flash loan providers on BSC
    address public constant VENUS_POOL = 0xfD36E2c2a6789Db23113685031d7F16329158384;
    
    // Events
    event ArbitrageExecuted(
        address indexed tokenIn,
        address indexed tokenOut,
        uint256 amountIn,
        uint256 profit,
        string buyDex,
        string sellDex
    );
    
    event FlashLoanExecuted(
        address indexed asset,
        uint256 amount,
        uint256 profit
    );
    
    // Arbitrage parameters
    struct ArbitrageParams {
        address tokenA;
        address tokenB;
        uint256 amountIn;
        address buyRouter;
        address sellRouter;
        uint24 buyFee;      // For V3 pools
        uint24 sellFee;     // For V3 pools
        bool useFlashLoan;
        address flashLoanProvider;
        uint256 minProfit;
    }
    
    // Flash loan callback data
    struct FlashLoanData {
        ArbitrageParams params;
        uint256 flashLoanAmount;
    }
    
    // Add new struct for triangular arbitrage
    struct TriangularArbitrageParams {
        address[] path;           // Array of token addresses in the triangular path (must be 3 or 4 tokens)
        address[] routers;        // Array of routers to use for each hop
        uint24[] fees;           // Array of fees for each hop (for PancakeSwap V3)
        uint256 amountIn;        // Amount of the first token to trade
        uint256 minProfitAmount; // Minimum profit required
        address flashLoanProvider; // Flash loan provider to use (0 for no flash loan)
    }
    
    // Add new struct for mempool backrun opportunity
    struct BackrunArbitrageParams {
        bytes32 targetTxHash;    // Transaction hash to backrun
        address[] path;          // Token path for the backrun
        address[] routers;       // Routers to use
        uint24[] fees;           // Fees for each hop (for PancakeSwap V3)
        uint256 amountIn;        // Amount to trade
        uint256 minProfitAmount; // Minimum profit required
        address flashLoanProvider; // Flash loan provider (0 for no flash loan)
        uint256 maxGasPrice;     // Maximum gas price to use
    }
    
    constructor() {}
    
    /**
     * @dev Execute triangular arbitrage across multiple DEXes
     * @param params Triangular arbitrage parameters
     * @return profit The profit amount in the first token
     */
    function executeTriangularArbitrage(TriangularArbitrageParams calldata params)
        external
        nonReentrant
        onlyOwner
        returns (uint256 profit)
    {
        require(params.path.length >= 3, "Invalid path length");
        require(params.path.length == params.routers.length + 1, "Invalid routers length");
        require(params.routers.length == params.fees.length, "Invalid fees length");
        
        if (params.flashLoanProvider != address(0)) {
            // Execute with flash loan
            return _executeFlashLoanTriangularArbitrage(params);
        } else {
            // Execute directly with available funds
            return _executeDirectTriangularArbitrage(params);
        }
    }
    
    /**
     * @dev Execute backrun arbitrage after a specific transaction
     * @param params Backrun arbitrage parameters
     * @return profit The profit amount in the first token
     */
    function executeBackrunArbitrage(BackrunArbitrageParams calldata params)
        external
        nonReentrant
        onlyOwner
        returns (uint256 profit)
    {
        require(params.path.length >= 2, "Invalid path length");
        require(params.path.length == params.routers.length + 1, "Invalid routers length");
        require(params.routers.length == params.fees.length, "Invalid fees length");
        require(tx.gasprice <= params.maxGasPrice, "Gas price too high");
        
        if (params.flashLoanProvider != address(0)) {
            // Execute with flash loan
            return _executeFlashLoanBackrunArbitrage(params);
        } else {
            // Execute directly with available funds
            return _executeDirectBackrunArbitrage(params);
        }
    }
    
    /**
     * @dev Execute triangular arbitrage directly with available funds
     * @param params Triangular arbitrage parameters
     * @return profit The profit amount in the first token
     */
    function _executeDirectTriangularArbitrage(TriangularArbitrageParams calldata params)
        internal
        returns (uint256 profit)
    {
        address firstToken = params.path[0];
        uint256 initialBalance = IERC20(firstToken).balanceOf(address(this));
        
        // Transfer tokens from sender if needed
        if (params.amountIn > 0) {
            IERC20(firstToken).safeTransferFrom(msg.sender, address(this), params.amountIn);
        }
        
        // Execute trades along the path
        uint256 currentAmount = IERC20(firstToken).balanceOf(address(this));
        for (uint i = 0; i < params.routers.length; i++) {
            address tokenIn = params.path[i];
            address tokenOut = params.path[i + 1];
            address router = params.routers[i];
            uint24 fee = params.fees[i];
            
            // Approve router to spend token
            IERC20(tokenIn).safeApprove(router, 0);
            IERC20(tokenIn).safeApprove(router, currentAmount);
            
            // Execute trade
            currentAmount = _executeTrade(
                tokenIn,
                tokenOut,
                currentAmount,
                router,
                fee,
                address(this)
            );
        }
        
        // Calculate profit
        uint256 finalBalance = IERC20(firstToken).balanceOf(address(this));
        profit = finalBalance > initialBalance ? finalBalance - initialBalance : 0;
        
        require(profit >= params.minProfitAmount, "Insufficient profit");
        
        return profit;
    }
    
    /**
     * @dev Execute backrun arbitrage directly with available funds
     * @param params Backrun arbitrage parameters
     * @return profit The profit amount in the first token
     */
    function _executeDirectBackrunArbitrage(BackrunArbitrageParams calldata params)
        internal
        returns (uint256 profit)
    {
        address firstToken = params.path[0];
        uint256 initialBalance = IERC20(firstToken).balanceOf(address(this));
        
        // Transfer tokens from sender if needed
        if (params.amountIn > 0) {
            IERC20(firstToken).safeTransferFrom(msg.sender, address(this), params.amountIn);
        }
        
        // Execute trades along the path
        uint256 currentAmount = IERC20(firstToken).balanceOf(address(this));
        for (uint i = 0; i < params.routers.length; i++) {
            address tokenIn = params.path[i];
            address tokenOut = params.path[i + 1];
            address router = params.routers[i];
            uint24 fee = params.fees[i];
            
            // Approve router to spend token
            IERC20(tokenIn).safeApprove(router, 0);
            IERC20(tokenIn).safeApprove(router, currentAmount);
            
            // Execute trade
            currentAmount = _executeTrade(
                tokenIn,
                tokenOut,
                currentAmount,
                router,
                fee,
                address(this)
            );
        }
        
        // Calculate profit
        uint256 finalBalance = IERC20(firstToken).balanceOf(address(this));
        profit = finalBalance > initialBalance ? finalBalance - initialBalance : 0;
        
        require(profit >= params.minProfitAmount, "Insufficient profit");
        
        return profit;
    }
    
    /**
     * @dev Execute triangular arbitrage using flash loan
     * @param params Triangular arbitrage parameters
     * @return profit The profit amount in the first token
     */
    function _executeFlashLoanTriangularArbitrage(TriangularArbitrageParams calldata params)
        internal
        returns (uint256 profit)
    {
        require(params.flashLoanProvider == VENUS_POOL, "Unsupported flash loan provider");
        
        address firstToken = params.path[0];
        uint256 flashLoanAmount = params.amountIn;
        
        // Prepare flash loan parameters for Venus
        address[] memory assets = new address[](1);
        assets[0] = firstToken;
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = flashLoanAmount;
        
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // 0 = no debt, just flash loan
        
        // Encode triangular arbitrage parameters for the callback
        bytes memory encodedParams = abi.encode(params);
        
        // Execute flash loan
        IVenusPool(VENUS_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            encodedParams,
            0 // referral code
        );
        
        // Profit calculation is handled in the callback
        uint256 finalBalance = IERC20(firstToken).balanceOf(address(this));
        return finalBalance;
    }
    
    /**
     * @dev Execute backrun arbitrage using flash loan
     * @param params Backrun arbitrage parameters
     * @return profit The profit amount in the first token
     */
    function _executeFlashLoanBackrunArbitrage(BackrunArbitrageParams calldata params)
        internal
        returns (uint256 profit)
    {
        require(params.flashLoanProvider == VENUS_POOL, "Unsupported flash loan provider");
        
        address firstToken = params.path[0];
        uint256 flashLoanAmount = params.amountIn;
        
        // Prepare flash loan parameters for Venus
        address[] memory assets = new address[](1);
        assets[0] = firstToken;
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = flashLoanAmount;
        
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // 0 = no debt, just flash loan
        
        // Encode backrun arbitrage parameters for the callback
        bytes memory encodedParams = abi.encode(params);
        
        // Execute flash loan
        IVenusPool(VENUS_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            encodedParams,
            0 // referral code
        );
        
        // Profit calculation is handled in the callback
        uint256 finalBalance = IERC20(firstToken).balanceOf(address(this));
        return finalBalance;
    }
    
    /**
     * @dev Execute cross-DEX arbitrage with or without flash loan
     */
    function executeArbitrage(ArbitrageParams calldata params) external onlyOwner nonReentrant {
        require(params.tokenA != address(0) && params.tokenB != address(0), "Invalid tokens");
        require(params.amountIn > 0, "Invalid amount");
        
        if (params.useFlashLoan) {
            _executeFlashLoanArbitrage(params);
        } else {
            _executeDirectArbitrage(params);
        }
    }
    
    /**
     * @dev Execute arbitrage with flash loan
     */
    function _executeFlashLoanArbitrage(ArbitrageParams memory params) internal {
        if (params.flashLoanProvider == VENUS_POOL) {
            _executeVenusFlashLoan(params);
        } else {
            revert("Unsupported flash loan provider");
        }
    }
    
    /**
     * @dev Execute Venus flash loan
     */
    function _executeVenusFlashLoan(ArbitrageParams memory params) internal {
        address[] memory assets = new address[](1);
        assets[0] = params.tokenA;
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // No debt
        
        FlashLoanData memory flashData = FlashLoanData({
            params: params,
            flashLoanAmount: params.amountIn
        });
        
        IVenusPool(VENUS_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            abi.encode(flashData),
            0
        );
    }
    
    /**
     * @dev Venus flash loan callback function
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == VENUS_POOL, "Unauthorized");
        require(initiator == address(this), "Invalid initiator");
        
        // Try to decode different types of arbitrage parameters
        // First, try to decode as regular arbitrage
        if (_tryExecuteRegularArbitrage(assets, amounts, premiums, params)) {
            return true;
        }
        
        // Try to decode as triangular arbitrage
        if (_tryExecuteTriangularArbitrage(assets, amounts, premiums, params)) {
            return true;
        }
        
        // Try to decode as backrun arbitrage
        if (_tryExecuteBackrunArbitrage(assets, amounts, premiums, params)) {
            return true;
        }
        
        revert("Unknown arbitrage type");
    }
    
    /**
     * @dev Try to execute regular cross-exchange arbitrage from flash loan callback
     */
    function _tryExecuteRegularArbitrage(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        bytes calldata params
    ) internal returns (bool) {
        // Try to decode the flash loan data for regular arbitrage
        try this.decodeRegularArbitrageParams(params) returns (FlashLoanData memory flashData) {
            // Execute arbitrage
            uint256 profit = _performArbitrageTrade(flashData.params);
            
            // Repay flash loan
            uint256 totalRepayment = amounts[0] + premiums[0];
            require(profit > totalRepayment, "Arbitrage not profitable");
            
            IERC20(assets[0]).safeTransfer(VENUS_POOL, totalRepayment);
            
            emit FlashLoanExecuted(assets[0], amounts[0], profit - totalRepayment);
            
            return true;
        } catch {
            return false;
        }
    }
    
    /**
     * @dev Try to execute triangular arbitrage from flash loan callback
     */
    function _tryExecuteTriangularArbitrage(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        bytes calldata params
    ) internal returns (bool) {
        // Try to decode the flash loan data for triangular arbitrage
        try this.decodeTriangularArbitrageParams(params) returns (TriangularArbitrageParams memory triangularParams) {
            address firstToken = triangularParams.path[0];
            uint256 initialBalance = IERC20(firstToken).balanceOf(address(this));
            
            // Execute trades along the path
            uint256 currentAmount = initialBalance;
            for (uint i = 0; i < triangularParams.routers.length; i++) {
                address tokenIn = triangularParams.path[i];
                address tokenOut = triangularParams.path[i + 1];
                address router = triangularParams.routers[i];
                uint24 fee = triangularParams.fees[i];
                
                // Approve router to spend token
                IERC20(tokenIn).safeApprove(router, 0);
                IERC20(tokenIn).safeApprove(router, currentAmount);
                
                // Execute trade
                currentAmount = _executeTrade(
                    tokenIn,
                    tokenOut,
                    currentAmount,
                    router,
                    fee,
                    address(this)
                );
            }
            
            // Repay the flash loan with premium
            uint256 totalRepayment = amounts[0] + premiums[0];
            IERC20(firstToken).safeTransfer(VENUS_POOL, totalRepayment);
            
            // Calculate profit
            uint256 finalBalance = IERC20(firstToken).balanceOf(address(this));
            uint256 profit = finalBalance > initialBalance ? finalBalance - initialBalance : 0;
            require(profit >= triangularParams.minProfitAmount, "Insufficient profit");
            
            emit FlashLoanExecuted(assets[0], amounts[0], profit);
            
            return true;
        } catch {
            return false;
        }
    }
    
    /**
     * @dev Try to execute backrun arbitrage from flash loan callback
     */
    function _tryExecuteBackrunArbitrage(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        bytes calldata params
    ) internal returns (bool) {
        // Try to decode the flash loan data for backrun arbitrage
        try this.decodeBackrunArbitrageParams(params) returns (BackrunArbitrageParams memory backrunParams) {
            address firstToken = backrunParams.path[0];
            uint256 initialBalance = IERC20(firstToken).balanceOf(address(this));
            
            // Execute trades along the path
            uint256 currentAmount = initialBalance;
            for (uint i = 0; i < backrunParams.routers.length; i++) {
                address tokenIn = backrunParams.path[i];
                address tokenOut = backrunParams.path[i + 1];
                address router = backrunParams.routers[i];
                uint24 fee = backrunParams.fees[i];
                
                // Approve router to spend token
                IERC20(tokenIn).safeApprove(router, 0);
                IERC20(tokenIn).safeApprove(router, currentAmount);
                
                // Execute trade
                currentAmount = _executeTrade(
                    tokenIn,
                    tokenOut,
                    currentAmount,
                    router,
                    fee,
                    address(this)
                );
            }
            
            // Repay the flash loan with premium
            uint256 totalRepayment = amounts[0] + premiums[0];
            IERC20(firstToken).safeTransfer(VENUS_POOL, totalRepayment);
            
            // Calculate profit
            uint256 finalBalance = IERC20(firstToken).balanceOf(address(this));
            uint256 profit = finalBalance > initialBalance ? finalBalance - initialBalance : 0;
            require(profit >= backrunParams.minProfitAmount, "Insufficient profit");
            
            emit FlashLoanExecuted(assets[0], amounts[0], profit);
            
            return true;
        } catch {
            return false;
        }
    }
    
    /**
     * @dev Helper function to decode regular arbitrage params
     * @notice External to allow try/catch pattern
     */
    function decodeRegularArbitrageParams(bytes calldata params) external pure returns (FlashLoanData memory) {
        return abi.decode(params, (FlashLoanData));
    }
    
    /**
     * @dev Helper function to decode triangular arbitrage params
     * @notice External to allow try/catch pattern
     */
    function decodeTriangularArbitrageParams(bytes calldata params) external pure returns (TriangularArbitrageParams memory) {
        return abi.decode(params, (TriangularArbitrageParams));
    }
    
    /**
     * @dev Helper function to decode backrun arbitrage params
     * @notice External to allow try/catch pattern
     */
    function decodeBackrunArbitrageParams(bytes calldata params) external pure returns (BackrunArbitrageParams memory) {
        return abi.decode(params, (BackrunArbitrageParams));
    }
    
    /**
     * @dev Execute arbitrage without flash loan
     */
    function _executeDirectArbitrage(ArbitrageParams memory params) internal {
        require(IERC20(params.tokenA).balanceOf(address(this)) >= params.amountIn, "Insufficient balance");
        
        uint256 profit = _performArbitrageTrade(params);
        require(profit >= params.minProfit, "Profit below minimum threshold");
    }
    
    /**
     * @dev Perform the actual arbitrage trade
     */
    function _performArbitrageTrade(ArbitrageParams memory params) internal returns (uint256) {
        uint256 initialBalance = IERC20(params.tokenA).balanceOf(address(this));
        
        // Step 1: Buy on cheaper DEX (tokenA -> tokenB)
        uint256 tokenBReceived = _executeTrade(
            params.tokenA,
            params.tokenB,
            params.amountIn,
            params.buyRouter,
            params.buyFee
        );
        
        // Step 2: Sell on expensive DEX (tokenB -> tokenA)
        uint256 tokenAReceived = _executeTrade(
            params.tokenB,
            params.tokenA,
            tokenBReceived,
            params.sellRouter,
            params.sellFee
        );
        
        uint256 finalBalance = IERC20(params.tokenA).balanceOf(address(this));
        uint256 profit = finalBalance > initialBalance ? finalBalance - initialBalance : 0;
        
        emit ArbitrageExecuted(
            params.tokenA,
            params.tokenB,
            params.amountIn,
            profit,
            _getRouterName(params.buyRouter),
            _getRouterName(params.sellRouter)
        );
        
        return profit;
    }
    
    /**
     * @dev Execute trade on specified router
     */
    function _executeTrade(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        address router,
        uint24 fee
    ) internal returns (uint256) {
        return _executeTrade(tokenIn, tokenOut, amountIn, router, fee, address(this));
    }
    
    /**
     * @dev Execute trade on specified router with custom recipient
     */
    function _executeTrade(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        address router,
        uint24 fee,
        address recipient
    ) internal returns (uint256) {
        IERC20(tokenIn).safeApprove(router, amountIn);
        
        if (router == PANCAKESWAP_V3_ROUTER) {
            // PancakeSwap V3 trade
            IPancakeV3Router.ExactInputSingleParams memory params = IPancakeV3Router.ExactInputSingleParams({
                tokenIn: tokenIn,
                tokenOut: tokenOut,
                fee: fee,
                recipient: recipient,
                deadline: block.timestamp + 300,
                amountIn: amountIn,
                amountOutMinimum: 0,
                sqrtPriceLimitX96: 0
            });
            
            return IPancakeV3Router(router).exactInputSingle(params);
        } else {
            // PancakeSwap V2 or other V2-compatible DEX trade
            address[] memory path = new address[](2);
            path[0] = tokenIn;
            path[1] = tokenOut;
            
            uint[] memory amounts = IPancakeRouter(router).swapExactTokensForTokens(
                amountIn,
                0, // Accept any amount of tokens out
                path,
                recipient,
                block.timestamp + 300
            );
            
            return amounts[1];
        }
    }
    
    /**
     * @dev Get router name for events
     */
    function _getRouterName(address router) internal pure returns (string memory) {
        if (router == PANCAKESWAP_V2_ROUTER) return "PancakeSwapV2";
        if (router == PANCAKESWAP_V3_ROUTER) return "PancakeSwapV3";
        if (router == BISWAP_ROUTER) return "BiSwap";
        if (router == APESWAP_ROUTER) return "ApeSwap";
        return "Unknown";
    }
    
    /**
     * @dev Emergency withdraw tokens
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner()).transfer(amount);
        } else {
            IERC20(token).safeTransfer(owner(), amount);
        }
    }
    
    /**
     * @dev Get quote for potential arbitrage
     */
    function getArbitrageQuote(
        address tokenA,
        address tokenB,
        uint256 amountIn,
        address buyRouter,
        address sellRouter,
        uint24 buyFee,
        uint24 sellFee
    ) external view returns (uint256 buyAmount, uint256 sellAmount, uint256 profit) {
        // Get buy quote
        if (buyRouter == PANCAKESWAP_V3_ROUTER) {
            // For V3, would need quoter contract (simplified here)
            buyAmount = amountIn; // Placeholder
        } else {
            address[] memory path = new address[](2);
            path[0] = tokenA;
            path[1] = tokenB;
            
            uint[] memory amounts = IPancakeRouter(buyRouter).getAmountsOut(amountIn, path);
            buyAmount = amounts[1];
        }
        
        // Get sell quote
        if (sellRouter == PANCAKESWAP_V3_ROUTER) {
            // For V3, would need quoter contract (simplified here)
            sellAmount = buyAmount; // Placeholder
        } else {
            address[] memory path = new address[](2);
            path[0] = tokenB;
            path[1] = tokenA;
            
            uint[] memory amounts = IPancakeRouter(sellRouter).getAmountsOut(buyAmount, path);
            sellAmount = amounts[1];
        }
        
        // Calculate profit
        if (sellAmount > amountIn) {
            profit = sellAmount - amountIn;
        } else {
            profit = 0;
        }
        
        return (buyAmount, sellAmount, profit);
    }
    
    /**
     * @dev Get triangular arbitrage quote for a given path of tokens and DEXes
     * @param path Array of token addresses in the triangular path
     * @param routers Array of routers to use for each hop
     * @param fees Array of fees for each hop (for V3 pools)
     * @param amountIn Amount of the first token to trade
     * @return finalAmount The final amount of the first token after completing the triangular trade
     * @return profit The profit amount in the first token
     */
    function getTriangularArbitrageQuote(
        address[] calldata path,
        address[] calldata routers,
        uint24[] calldata fees,
        uint256 amountIn
    ) external view returns (uint256 finalAmount, uint256 profit) {
        require(path.length >= 3, "Invalid path length");
        require(path.length == routers.length + 1, "Invalid routers length");
        require(routers.length == fees.length, "Invalid fees length");
        
        uint256 currentAmount = amountIn;
        
        // Simulate trades along the path
        for (uint i = 0; i < routers.length; i++) {
            address tokenIn = path[i];
            address tokenOut = path[i + 1];
            address router = routers[i];
            uint24 fee = fees[i];
            
            // Get quote for this hop
            if (router == PANCAKESWAP_V3_ROUTER) {
                // TODO: Implement V3 quote logic
                // For now, we'll just return 0 to indicate that V3 quotes are not implemented
                return (0, 0);
            } else {
                address[] memory tradePath = new address[](2);
                tradePath[0] = tokenIn;
                tradePath[1] = tokenOut;
                
                uint[] memory amounts = IPancakeRouter(router).getAmountsOut(currentAmount, tradePath);
                currentAmount = amounts[1];
            }
        }
        
        finalAmount = currentAmount;
        
        // Calculate profit
        if (finalAmount > amountIn) {
            profit = finalAmount - amountIn;
        } else {
            profit = 0;
        }
        
        return (finalAmount, profit);
    }
    
    /**
     * @dev Get backrun arbitrage quote for a given path of tokens and DEXes
     * @param path Array of token addresses in the backrun path
     * @param routers Array of routers to use for each hop
     * @param fees Array of fees for each hop (for V3 pools)
     * @param amountIn Amount of the first token to trade
     * @return finalAmount The final amount of the first token after completing the backrun trade
     * @return profit The profit amount in the first token
     */
    function getBackrunArbitrageQuote(
        address[] calldata path,
        address[] calldata routers,
        uint24[] calldata fees,
        uint256 amountIn
    ) external view returns (uint256 finalAmount, uint256 profit) {
        require(path.length >= 2, "Invalid path length");
        require(path.length == routers.length + 1, "Invalid routers length");
        require(routers.length == fees.length, "Invalid fees length");
        
        uint256 currentAmount = amountIn;
        
        // Simulate trades along the path
        for (uint i = 0; i < routers.length; i++) {
            address tokenIn = path[i];
            address tokenOut = path[i + 1];
            address router = routers[i];
            uint24 fee = fees[i];
            
            // Get quote for this hop
            if (router == PANCAKESWAP_V3_ROUTER) {
                // TODO: Implement V3 quote logic
                // For now, we'll just return 0 to indicate that V3 quotes are not implemented
                return (0, 0);
            } else {
                address[] memory tradePath = new address[](2);
                tradePath[0] = tokenIn;
                tradePath[1] = tokenOut;
                
                uint[] memory amounts = IPancakeRouter(router).getAmountsOut(currentAmount, tradePath);
                currentAmount = amounts[1];
            }
        }
        
        finalAmount = currentAmount;
        
        // Calculate profit
        if (finalAmount > amountIn) {
            profit = finalAmount - amountIn;
        } else {
            profit = 0;
        }
        
        return (finalAmount, profit);
    }
    
    receive() external payable {}
}