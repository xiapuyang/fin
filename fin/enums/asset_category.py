from enum import StrEnum


class AssetCategory(StrEnum):
    """Stable asset category identifiers used in rebalance bucket classification.

    IDs are immutable once deployed — they are stored in user configs.
    Add new values; never rename or remove existing ones.
    """

    EQUITY_US = "equity_us"
    EQUITY_HK = "equity_hk"
    EQUITY_CN = "equity_cn"
    INDEX_FUND_US = "index_fund_us"
    INDEX_FUND_HK = "index_fund_hk"
    INDEX_FUND_CN = "index_fund_cn"
    ETF_GLOBAL = "etf_global"
    BOND_US = "bond_us"
    BOND_GLOBAL = "bond_global"
    CRYPTO = "crypto"
    REIT = "reit"
