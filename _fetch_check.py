#!/usr/bin/env python3
"""Fetch PLS data and check for 26125"""
import sys
sys.path.insert(0, '.')
from scripts.data_fetcher import fetch_pls, save_incremental
import pandas as pd

print('=== Fetching PLS ===')
pls_data = fetch_pls(30)
if pls_data:
    print(f'Got {len(pls_data)} PLS records')
    print(f'Latest: {pls_data[0]}')
    latest_issue = pls_data[0]["期号"]
    if latest_issue == '26125':
        print('>>> 26125 FOUND! Saving...')
        save_incremental(pd.DataFrame(pls_data), 'pls')
    else:
        print(f'>>> Latest is {latest_issue}, NOT 26125')
else:
    print('>>> No PLS data fetched')
