# Contributing to ArbitrageWise

Thank you for your interest in contributing to ArbitrageWise! This document provides guidelines and instructions for contributing to this project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How to Contribute

### Reporting Bugs

Bugs are tracked as GitHub issues. Create an issue and provide the following information:

- Use a clear and descriptive title
- Describe the exact steps to reproduce the bug
- Provide specific examples to demonstrate the steps
- Describe the behavior you observed and what you expected to see
- Include screenshots if applicable
- Include details about your environment (OS, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are also tracked as GitHub issues. Provide the following information:

- Use a clear and descriptive title
- Provide a detailed description of the suggested enhancement
- Explain why this enhancement would be useful
- Include examples of how the enhancement would be used

### Pull Requests

1. Fork the repository
2. Create a new branch for your feature or bugfix
3. Make your changes
4. Run tests to ensure your changes don't break existing functionality
5. Submit a pull request

#### Pull Request Guidelines

- Follow the coding style of the project
- Include tests for new features or bug fixes
- Update documentation as needed
- Keep pull requests focused on a single topic
- Reference any relevant issues

## Development Setup

1. Clone the repository
   ```bash
   git clone https://github.com/yourusername/ArbitrageWise-Refined.git
   cd ArbitrageWise-Refined
   ```

2. Create a virtual environment
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

4. Install development dependencies
   ```bash
   pip install -e .
   ```

5. Configure environment variables
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   # Set MAINNET=False for development/testing
   # Set MAINNET=True for production deployment
   ```

## Network Configuration

ArbitrageWise uses a centralized network configuration system controlled by the `MAINNET` environment variable:

- **Development/Testing**: Set `MAINNET=False` to use testnets (Sepolia, BSC Testnet, Mumbai)
- **Production**: Set `MAINNET=True` to use mainnets (Ethereum, BSC, Polygon)

This single variable automatically configures:
- Chain IDs and RPC URLs
- Token contract addresses  
- DEX router and factory addresses
- All blockchain service configurations

## Testing

Run tests using the test runner:

```bash
python tests/run_tests.py
```

Or run specific test modules:

```bash
python tests/run_tests.py -m test_arbitrage_strategies test_mempool_monitor
```

Test the network configuration system:

```bash
python test_network_config.py
```

This validates that the `MAINNET` environment variable correctly switches all blockchain services between mainnet and testnet configurations.

## Code Style

This project follows these coding conventions:

- Use [Black](https://github.com/psf/black) for code formatting
- Use [isort](https://github.com/PyCQA/isort) for import sorting
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines
- Use type hints where appropriate

You can automatically format your code with:

```bash
black .
isort .
```

## Documentation

- Update documentation when changing code
- Use docstrings for functions, classes, and modules
- Follow [Google style docstrings](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html)

## License

By contributing to ArbitrageWise, you agree that your contributions will be licensed under the project's MIT License.