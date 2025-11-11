# -*- coding: utf-8 -*-
import os
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
import pandas as pd

from utils import CHAIN_PRESETS, normalize_hex, safe_get


def _auth_header_covalent():
    key = os.getenv("COVALENT_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def fetch_total_supply(chain: str, token: str):
    """
    Try Covalent first (rich metadata), fallback to Ethplorer (Ethereum only).
    Returns: (total_supply_raw, decimals, name, symbol) or (None, None, None, None)
    """
    # Covalent
    cov_key = os.getenv("COVALENT_API_KEY", "").strip()
    if cov_key:
        cfg = CHAIN_PRESETS[chain]
        url = f"https://api.covalenthq.com/v1/{cfg['covalent_chain']}/tokens/{token}/token_holders/?page-size=1"
        r = requests.get(url, headers=_auth_header_covalent(), timeout=30)
        if r.ok:
            data = r.json()
            items = safe_get(data, ["data","items"], [])
            if items:
                meta = safe_get(items, [0,"contract_metadata"], {})
                sup = normalize_hex(meta.get("total_supply")) if meta else None
                dec = meta.get("decimals")
                name = meta.get("name") or ""
                sym = meta.get("symbol") or ""
                if sup is not None and dec is not None:
                    return int(sup), int(dec), name, sym

    # Ethplorer (Ethereum only)
    eth_key = os.getenv("ETHPLORER_API_KEY", "freekey").strip() or "freekey"
    if chain == "ethereum":
        url = f"https://api.ethplorer.io/getTokenInfo/{token}?apiKey={eth_key}"
        r = requests.get(url, timeout=30)
        if r.ok:
            j = r.json()
            sup = j.get("totalSupply")
            dec = j.get("decimals", 18)
            name = j.get("name","")
            sym = j.get("symbol","")
            if sup is not None:
                try:
                    if isinstance(sup, str) and sup.startswith("0x"):
                        sup = int(sup, 16)
                    else:
                        sup = int(sup)
                    return int(sup), int(dec), name, sym
                except Exception:
                    pass

    return None, None, None, None


def fetch_token_holders_covalent(chain: str, token: str, top_n: int = 500) -> Optional[pd.DataFrame]:
    key = os.getenv("COVALENT_API_KEY","").strip()
    if not key:
        return None
    cfg = CHAIN_PRESETS[chain]
    url = f"https://api.covalenthq.com/v1/{cfg['covalent_chain']}/tokens/{token}/token_holders/?page-size={min(top_n,10000)}"
    r = requests.get(url, headers=_auth_header_covalent(), timeout=60)
    if not r.ok:
        return None
    data = r.json()
    items = safe_get(data, ["data","items"], [])
    rows = []
    seen = set()
    for it in items[:top_n]:
        addr = it.get("address")
        if not addr or addr in seen:
            continue
        seen.add(addr)
        bal_hex = normalize_hex(safe_get(it, ["balance"]))
        txs = it.get("transfer_count")
        rows.append({
            "address": addr,
            "balance_raw": int(bal_hex) if bal_hex is not None else 0,
            "tx_count": txs,
        })
    return pd.DataFrame(rows)


def fetch_token_holders_ethplorer(chain: str, token: str, top_n: int = 500) -> Optional[pd.DataFrame]:
    if chain != "ethereum":
        return None
    key = os.getenv("ETHPLORER_API_KEY", "freekey").strip() or "freekey"
    url = f"https://api.ethplorer.io/getTopTokenHolders/{token}?apiKey={key}&limit={min(top_n,1000)}"
    r = requests.get(url, timeout=60)
    if not r.ok:
        return None
    j = r.json()
    holders = j.get("holders", [])
    rows = []
    for h in holders[:top_n]:
        rows.append({
            "address": h.get("address"),
            "balance_raw": int(float(h.get("balance", 0))),  # Ethplorer returns human units; but we don't know decimals here
            "tx_count": None,
        })
    return pd.DataFrame(rows)


def fetch_token_transfers_covalent(chain: str, token: str,
                                   start_time: Optional[datetime]=None,
                                   end_time: Optional[datetime]=None,
                                   max_pages: int = 5) -> Optional[pd.DataFrame]:
    key = os.getenv("COVALENT_API_KEY","").strip()
    if not key:
        return None
    cfg = CHAIN_PRESETS[chain]
    # Covalent "transfers" endpoint via /events/topics for Transfer signature
    # We filter by date; pagination by page-number
    topic = "Transfer(address,address,uint256)"
    base = f"https://api.covalenthq.com/v1/{cfg['covalent_chain']}/events/topics/"
    # ABI signature hash precomputed by Covalent; we can pass the string, Covalent accepts "signature=Transfer..." query
    params = {
        "sender-address": token,
        "match-contract-address": token,
        "page-size": 1000,
        "starting-block": "",
        "ending-block": "",
        "from-date": start_time.strftime("%Y-%m-%d") if start_time else "",
        "to-date": end_time.strftime("%Y-%m-%d") if end_time else "",
        "key": key  # legacy param still accepted; also support header
    }
    rows = []
    for page in range(1, max_pages+1):
        params["page-number"] = page
        r = requests.get(base, params=params, headers=_auth_header_covalent(), timeout=60)
        if not r.ok:
            break
        data = r.json()
        evs = data.get("data", {}).get("items", [])
        if not evs:
            break
        for e in evs:
            # Covalent decodes params
            decoded = e.get("decoded", {})
            dec = decoded.get("params", [])
            fr = None; to = None; val = None
            for prm in dec:
                if prm.get("name") == "from":
                    fr = prm.get("value")
                elif prm.get("name") == "to":
                    to = prm.get("value")
                elif prm.get("name") == "value":
                    v = prm.get("value")
                    try:
                        val = int(v)
                    except Exception:
                        val = None
            ts = e.get("block_signed_at")
            rows.append({
                "block_signed_at": ts,
                "tx_hash": e.get("tx_hash"),
                "from": fr,
                "to": to,
                "value_raw": val,
            })
        # Stop early if last page size less than page-size
        if len(evs) < 1000:
            break
        time.sleep(0.2)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_contract_creation_tx_etherscan(chain: str, token: str) -> Tuple[Optional[str], Optional[datetime]]:
    cfg = CHAIN_PRESETS[chain]
    base = cfg["explorer_api"]
    key_env = cfg["explorer_key_env"]
    api_key = os.getenv(key_env, "").strip()
    if not api_key:
        return None, None
    # Etherscan-compatible "getcontractcreation" (for contracts) via 'contract' module
    url = f"{base}?module=contract&action=getcontractcreation&contractaddresses={token}&apikey={api_key}"
    r = requests.get(url, timeout=30)
    if not r.ok:
        return None, None
    j = r.json()
    res = j.get("result", [])
    if not res:
        return None, None
    creator = res[0].get("contractCreator")
    tx_hash = res[0].get("txHash")
    # Fetch tx to get timestamp
    url2 = f"{base}?module=proxy&action=eth_getTransactionByHash&txhash={tx_hash}&apikey={api_key}"
    r2 = requests.get(url2, timeout=30)
    if not r2.ok:
        return creator, None
    j2 = r2.json()
    # Some explorers don't return timestamp here; use tx receipt block then get block time
    # Get receipt for block number
    url3 = f"{base}?module=proxy&action=eth_getTransactionReceipt&txhash={tx_hash}&apikey={api_key}"
    r3 = requests.get(url3, timeout=30)
    if not r3.ok:
        return creator, None
    j3 = r3.json()
    block_hex = j3.get("result", {}).get("blockNumber")
    if not block_hex:
        return creator, None
    # Block by number
    url4 = f"{base}?module=proxy&action=eth_getBlockByNumber&tag={block_hex}&boolean=true&apikey={api_key}"
    r4 = requests.get(url4, timeout=30)
    if not r4.ok:
        return creator, None
    j4 = r4.json()
    ts_hex = j4.get("result", {}).get("timestamp")
    if not ts_hex:
        return creator, None
    try:
        ts = int(ts_hex, 16)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        dt = None
    return creator, dt
