# -*- coding: utf-8 -*-
import os
from typing import Any, List, Dict

import pandas as pd


CHAIN_PRESETS = {
    # You can extend with more chains later (bsc, polygon, etc.).
    "ethereum": {
        "explorer_api": "https://api.etherscan.io/api",
        "explorer_key_env": "ETHERSCAN_API_KEY",
        "covalent_chain": "eth-mainnet",
    },
    "polygon": {
        "explorer_api": "https://api.polygonscan.com/api",
        "explorer_key_env": "POLYGONSCAN_API_KEY",
        "covalent_chain": "matic-mainnet",
    },
    "bsc": {
        "explorer_api": "https://api.bscscan.com/api",
        "explorer_key_env": "BSCSCAN_API_KEY",
        "covalent_chain": "bsc-mainnet",
    },
    "arbitrum": {
        "explorer_api": "https://api.arbiscan.io/api",
        "explorer_key_env": "ARBISCAN_API_KEY",
        "covalent_chain": "arbitrum-mainnet",
    },
    "optimism": {
        "explorer_api": "https://api-optimistic.etherscan.io/api",
        "explorer_key_env": "OPTIMISTIC_ETHERSCAN_API_KEY",
        "covalent_chain": "optimism-mainnet",
    },
}


def ensure_provider_priority(pref: str) -> None:
    if pref == "auto":
        return
    # No-op placeholder to validate string; could add more checks later.


def read_team_list(path: str) -> List[str]:
    addrs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            addrs.append(s)
    return addrs


def to_excel_autofit(xw, df: pd.DataFrame, sheet_name: str):
    df.to_excel(xw, sheet_name=sheet_name, index=False)
    # Best-effort: let Excel handle widths; openpyxl autosize isn't reliable without heavy loops.


def format_pct(x: float) -> str:
    try:
        return f"{x*100:.4f}%"
    except Exception:
        return ""


def normalize_hex(v: Any):
    if v is None:
        return None
    if isinstance(v, str):
        if v.startswith("0x"):
            return int(v, 16)
        try:
            return int(v)
        except Exception:
            return None
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except Exception:
            return None
    return None


def safe_get(obj: Dict, path: List[str], default=None):
    cur = obj
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur
