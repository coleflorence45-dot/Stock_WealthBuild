import requests
import pandas as pd
from datetime import datetime, timedelta

def get_insider_buys():
    # SEC EDGAR full-text search for Form 4 filings
    url = "https://efts.sec.gov/LATEST/search-index?q=%22form+4%22&dateRange=custom&startdt={}&enddt={}&forms=4"
    
    today = datetime.today()
    week_ago = today - timedelta(days=7)
    
    response = requests.get(
        url.format(week_ago.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')),
        headers={"User-Agent": "yourname yourname@email.com"}  # SEC requires this
    )
    
    return response.json()