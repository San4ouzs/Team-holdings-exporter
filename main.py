#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Team Holdings Exporter
Collects token holder data from public APIs and applies heuristics to estimate
the share held by project team (dev/foundation/vesting/multisig etc.).
Outputs a clean Excel file with multiple sheets.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from dotenv import load_dotenv

from providers import (
    fetch_total_supply,
    fetch_token_holders_covalent,
    fetch_token_holders_ethplorer,
    fetch_token_transfers_covalent,
    get_contract_creation_tx_etherscan,
)
from heuristics import (
    infer_team_wallets_from_transfers,
    normalize_address,
)
from utils import (
    to_excel_autofit,
    read_team_list,
    format_pct,
    CHAIN_PRESETS,
    ensure_provider_priority,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export likely team-owned token holdings to Excel."
    )
    p.add_argument("--chain", required=True, choices=list(CHAIN_PRESETS.keys()),
                   help="Target network (affects API routing).")
    p.add_argument("--token", required=True,
                   help="ERC-20 (or chain-equivalent) token contract address.")
    p.add_argument("--provider", default="auto", choices=["auto","covalent","ethplorer"],
                   help="Primary data source for holders (fallbacks used as needed).")
    p.add_argument("--top", type=int, default=500,
                   help="Max holders to fetch (per provider limits).")
    p.add_argument("--hours", type=int, default=48,
                   help="Window after contract creation to treat outbound allocations as 'initial'.")
    p.add_argument("--team-file", type=str, default=None,
                   help="Path to newline-delimited list of known team addresses (optional).")
    p.add_argument("--label-map", type=str, default=None,
                   help="Path to CSV with columns address,label (optional).")
    p.add_argument("--out", type=str, default=None,
                   help="Output Excel filename (default: team_holdings_<token>_<date>.xlsx)")
    p.add_argument("--include-transfers", action="store_true",
                   help="Add a sheet with early transfer details (for auditability).")
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    chain = args.chain
    token = normalize_address(args.token)
    top_n = args.top
    hours = args.hours
    provider_pref = args.provider

    chain_cfg = CHAIN_PRESETS[chain]
    ensure_provider_priority(provider_pref)

    # Prepare output path
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = args.out or f"team_holdings_{chain}_{token[:6]}_{date_str}.xlsx"

    # Load optional user-supplied known team addresses
    known_team = set()
    if args.team_file:
        known_team = {normalize_address(a) for a in read_team_list(args.team_file)}

    label_map = {}
    if args.label_map and os.path.exists(args.label_map):
        df_labels = pd.read_csv(args.label_map)
        for _, row in df_labels.iterrows():
            addr = normalize_address(str(row["address"]))
            label_map[addr] = str(row.get("label", "")).strip()

    # 1) Supply
    total_supply, token_decimals, token_name, token_symbol = fetch_total_supply(chain, token)
    if total_supply is None:
        print("ERROR: Could not fetch token total supply. Check API keys/connectivity.", file=sys.stderr)
        sys.exit(2)

    # 2) Holders via preferred provider
    holders_df = None
    if provider_pref in ("auto", "covalent"):
        holders_df = fetch_token_holders_covalent(chain, token, top_n=top_n)
    if holders_df is None and provider_pref in ("auto", "ethplorer"):
        holders_df = fetch_token_holders_ethplorer(chain, token, top_n=top_n)

    if holders_df is None or holders_df.empty:
        print("ERROR: No holders data returned. Try a different provider or smaller --top.", file=sys.stderr)
        sys.exit(3)

    # Normalize + compute pct of supply
    holders_df["address_n"] = holders_df["address"].map(normalize_address)
    holders_df = holders_df.drop_duplicates(subset=["address_n"])
    holders_df["balance_tokens"] = holders_df["balance_raw"] / (10 ** token_decimals)
    holders_df["pct_total_supply"] = holders_df["balance_raw"] / total_supply

    # 3) Contract creation + early transfers for heuristics
    creator_addr, creation_time = get_contract_creation_tx_etherscan(chain, token)
    early_transfers_df = pd.DataFrame()
    inferred_team_addrs = set()
    if creation_time is not None:
        window_end = creation_time + timedelta(hours=hours)
        transfers_df = fetch_token_transfers_covalent(
            chain, token, start_time=creation_time, end_time=window_end, max_pages=10
        )
        if transfers_df is not None and not transfers_df.empty:
            inferred_team_addrs, early_transfers_df = infer_team_wallets_from_transfers(
                transfers_df, token_contract=token, creator_addr=creator_addr
            )

    # 4) Label + mark team
    holders_df["label"] = holders_df["address_n"].map(label_map).fillna("")
    holders_df["is_known_team"] = holders_df["address_n"].isin(known_team)
    holders_df["is_inferred_team"] = holders_df["address_n"].isin(inferred_team_addrs)
    holders_df["is_team"] = holders_df[["is_known_team","is_inferred_team"]].any(axis=1)

    # 5) Summaries
    team_df = holders_df[holders_df["is_team"]].copy()
    nonteam_df = holders_df[~holders_df["is_team"]].copy()

    summary_rows = []
    def add_row(name, df):
        bal = df["balance_raw"].sum() if not df.empty else 0
        summary_rows.append({
            "category": name,
            "wallets": 0 if df is None else len(df),
            "balance_tokens": bal / (10 ** token_decimals),
            "pct_total_supply": bal / total_supply,
        })

    add_row("Known team (provided)", holders_df[holders_df["is_known_team"]])
    add_row("Inferred team (heuristics)", holders_df[holders_df["is_inferred_team"]])
    add_row("All team (union)", team_df)
    add_row("Non-team (others in sample)", nonteam_df)

    summary_df = pd.DataFrame(summary_rows)
    meta_df = pd.DataFrame([{
        "token_name": token_name,
        "token_symbol": token_symbol,
        "token_address": token,
        "chain": chain,
        "total_supply_tokens": total_supply / (10 ** token_decimals),
        "decimals": token_decimals,
        "creator_address": creator_addr or "",
        "creation_time_utc": creation_time.isoformat() if creation_time else "",
        "holders_sample": len(holders_df),
        "hours_window": hours,
        "provider": "covalent/ethplorer mixed" if provider_pref=="auto" else provider_pref,
        "generated_at_utc": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
    }])

    # 6) Export to Excel
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        to_excel_autofit(xw, meta_df, "Meta")
        to_excel_autofit(xw, summary_df.assign(
            pct_total_supply=summary_df["pct_total_supply"].map(format_pct)
        ), "Summary")

        cols = ["address_n","label","is_known_team","is_inferred_team","is_team",
                "balance_tokens","pct_total_supply","tx_count"]
        # Some providers don't give tx_count; fill if missing
        if "tx_count" not in holders_df.columns:
            holders_df["tx_count"] = None

        export_df = holders_df.copy()
        export_df["pct_total_supply"] = export_df["pct_total_supply"].map(format_pct)
        export_df = export_df.rename(columns={
            "address_n":"address",
        })
        to_excel_autofit(xw, export_df[cols], "Wallets")

        if args.include_transfers and early_transfers_df is not None and not early_transfers_df.empty:
            to_excel_autofit(xw, early_transfers_df, "EarlyTransfers")

        # Methodology sheet
        methodology = [
            ["Item","Value"],
            ["Known team list", args.team_file or "(none)"],
            ["Label map", args.label_map or "(none)"],
            ["Heuristic window (hours)", hours],
            ["Heuristic rule",
             "Addresses that received tokens from creator/deployer within the first N hours after creation are flagged as inferred team."],
            ["Caveats",
             "Results are estimates based on available holders sample and heuristics; manual review recommended."],
        ]
        meth_df = pd.DataFrame(methodology[1:], columns=methodology[0])
        to_excel_autofit(xw, meth_df, "Methodology")

    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
