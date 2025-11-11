# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Tuple, Set

import pandas as pd


def normalize_address(addr: str) -> str:
    return (addr or "").lower()


def infer_team_wallets_from_transfers(transfers_df: pd.DataFrame,
                                      token_contract: str,
                                      creator_addr: str | None) -> Tuple[Set[str], pd.DataFrame]:
    """
    Heuristic: team wallets are those that receive from creator OR from token contract
    (common for vesting mints) in the earliest window.
    """
    df = transfers_df.copy()
    df["from_n"] = df["from"].map(normalize_address)
    df["to_n"] = df["to"].map(normalize_address)

    creator_n = normalize_address(creator_addr) if creator_addr else None
    token_n = normalize_address(token_contract)

    team_like = set()

    # Received from creator
    if creator_n:
        team_like.update(df.loc[df["from_n"] == creator_n, "to_n"].dropna().tolist())

    # Received from token contract (minting/vesting)
    team_like.update(df.loc[df["from_n"] == token_n, "to_n"].dropna().tolist())

    # Remove burn/zero address if present
    team_like.discard("0x0000000000000000000000000000000000000000")

    # Prepare human-readable table
    out = df[df["to_n"].isin(team_like)].copy()
    out = out[["block_signed_at","tx_hash","from","to","value_raw"]].sort_values("block_signed_at")

    return team_like, out
