from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]

setup(
    name="arbitragewise-refined",
    version="2.0.0",
    author="ArbitrageWise Development Team",
    author_email="dev@arbitragewise.com",
    description="Production-Ready Multi-Chain DEX Arbitrage System with Centralized Network Configuration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/ArbitrageWise-Refined",
    packages=find_packages(exclude=["tests*", "docs*"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Financial and Insurance Industry",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Framework :: AsyncIO",
    ],
    keywords="arbitrage, defi, blockchain, ethereum, bsc, polygon, solana, dex, trading, cryptocurrency",
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.3.0",
            "isort>=5.12.0",
            "mypy>=1.3.0",
            "flake8>=6.0.0",
        ],
        "monitoring": [
            "prometheus-client>=0.17.0",
            "grafana-api>=1.0.3",
        ],
        "advanced": [
            "brownie-contracts>=1.1.0",
            "uniswap-python>=0.6.0",
            "dydx-v3-python>=1.0.0",
            "aave-v3-py>=0.1.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "arbitragewise=main:main",
            "arbitragewise-test=test_network_config:test_network_switching",
        ],
    },
    package_data={
        "dex": [
            "shared/contracts/*.json",
            "*/contracts/*.json",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    project_urls={
        "Bug Reports": "https://github.com/yourusername/ArbitrageWise-Refined/issues",
        "Source": "https://github.com/yourusername/ArbitrageWise-Refined",
        "Documentation": "https://github.com/yourusername/ArbitrageWise-Refined/blob/main/README.md",
    },
)