"""
Google Trends Analysis: "Brandon Bottin" search frequency and location data since 2004.
"""

import json
import time
import pandas as pd
from pytrends.request import TrendReq

def fetch_trends_data():
    """Fetch Google Trends data for 'Brandon Bottin' since 2004."""
    
    pytrends = TrendReq(hl='en-US', tz=360)
    keyword = 'Brandon Bottin'
    
    print(f"Fetching Google Trends data for: '{keyword}'")
    print("=" * 60)
    
    # Build payload for interest over time (2004 to present)
    pytrends.build_payload(
        kw_list=[keyword],
        cat=0,
        timeframe='2004-01-01 2026-02-16',
        geo='',
        gprop=''
    )
    
    # 1. Interest Over Time
    print("\n--- INTEREST OVER TIME (2004-present) ---\n")
    try:
        interest_over_time = pytrends.interest_over_time()
        if interest_over_time.empty:
            print("No interest over time data found for this keyword.")
            print("This means the search volume is too low for Google Trends to report.")
        else:
            # Drop the isPartial column if present
            if 'isPartial' in interest_over_time.columns:
                interest_over_time = interest_over_time.drop(columns=['isPartial'])
            
            print(f"Data points: {len(interest_over_time)}")
            print(f"\nMonths with search activity (value > 0):")
            active = interest_over_time[interest_over_time[keyword] > 0]
            if active.empty:
                print("  No months with detectable search activity.")
            else:
                for date, row in active.iterrows():
                    print(f"  {date.strftime('%Y-%m')}: {row[keyword]}")
            
            print(f"\nPeak interest: {interest_over_time[keyword].max()}")
            peak_date = interest_over_time[keyword].idxmax()
            print(f"Peak month: {peak_date.strftime('%Y-%m')}")
            print(f"Average interest: {interest_over_time[keyword].mean():.2f}")
            
            # Save to CSV
            interest_over_time.to_csv('/workspace/interest_over_time.csv')
            print("\nSaved interest over time data to interest_over_time.csv")
    except Exception as e:
        print(f"Error fetching interest over time: {e}")
        interest_over_time = pd.DataFrame()
    
    time.sleep(2)  # Rate limiting
    
    # 2. Interest by Region
    print("\n--- INTEREST BY REGION ---\n")
    try:
        # Re-build payload for region data
        pytrends.build_payload(
            kw_list=[keyword],
            cat=0,
            timeframe='2004-01-01 2026-02-16',
            geo='',
            gprop=''
        )
        interest_by_region = pytrends.interest_by_region(resolution='COUNTRY', inc_low_vol=True, inc_geo_code=True)
        
        if interest_by_region.empty:
            print("No regional data found for this keyword.")
            print("This means the search volume is too low for Google Trends to report regional breakdowns.")
        else:
            # Filter to regions with > 0 interest
            active_regions = interest_by_region[interest_by_region[keyword] > 0].sort_values(
                by=keyword, ascending=False
            )
            
            if active_regions.empty:
                print("No regions with detectable search activity.")
            else:
                print(f"Regions with search activity ({len(active_regions)} regions):\n")
                for region, row in active_regions.iterrows():
                    print(f"  {region}: {row[keyword]}")
                
                top_region = active_regions.index[0]
                top_value = active_regions.iloc[0][keyword]
                print(f"\nTop region: {top_region} (interest score: {top_value})")
            
            # Save to CSV
            interest_by_region.to_csv('/workspace/interest_by_region.csv')
            print("\nSaved regional data to interest_by_region.csv")
    except Exception as e:
        print(f"Error fetching interest by region: {e}")
    
    time.sleep(2)  # Rate limiting
    
    # 3. Try US-specific state-level data
    print("\n--- INTEREST BY US STATE ---\n")
    try:
        pytrends.build_payload(
            kw_list=[keyword],
            cat=0,
            timeframe='2004-01-01 2026-02-16',
            geo='US',
            gprop=''
        )
        interest_by_state = pytrends.interest_by_region(resolution='REGION', inc_low_vol=True, inc_geo_code=True)
        
        if interest_by_state.empty:
            print("No US state-level data found.")
        else:
            active_states = interest_by_state[interest_by_state[keyword] > 0].sort_values(
                by=keyword, ascending=False
            )
            
            if active_states.empty:
                print("No US states with detectable search activity.")
            else:
                print(f"US states with search activity ({len(active_states)} states):\n")
                for state, row in active_states.iterrows():
                    print(f"  {state}: {row[keyword]}")
                
                top_state = active_states.index[0]
                top_state_val = active_states.iloc[0][keyword]
                print(f"\nTop US state: {top_state} (interest score: {top_state_val})")
            
            interest_by_state.to_csv('/workspace/interest_by_us_state.csv')
            print("\nSaved US state data to interest_by_us_state.csv")
    except Exception as e:
        print(f"Error fetching US state data: {e}")
    
    # 4. Related queries
    time.sleep(2)
    print("\n--- RELATED QUERIES ---\n")
    try:
        pytrends.build_payload(
            kw_list=[keyword],
            cat=0,
            timeframe='2004-01-01 2026-02-16',
            geo='',
            gprop=''
        )
        related_queries = pytrends.related_queries()
        
        if related_queries and keyword in related_queries:
            rq = related_queries[keyword]
            if rq['top'] is not None and not rq['top'].empty:
                print("Top related queries:")
                print(rq['top'].to_string())
            else:
                print("No top related queries found.")
            
            if rq['rising'] is not None and not rq['rising'].empty:
                print("\nRising related queries:")
                print(rq['rising'].to_string())
            else:
                print("No rising related queries found.")
        else:
            print("No related queries data available.")
    except Exception as e:
        print(f"Error fetching related queries: {e}")
    
    print("\n" + "=" * 60)
    print("Analysis complete.")


if __name__ == '__main__':
    fetch_trends_data()
