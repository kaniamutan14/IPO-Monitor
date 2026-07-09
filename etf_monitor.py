import logging
import time
import random
import traceback
import sys
from datetime import datetime
from nse_client import NSEClient
import discord_notifier

MIN_VOLUME = 200000
MIN_PROFIT_PERCENT = 0.7
DELAY_BETWEEN_CHECKS = 20
SESSION_REFRESH_EVERY = 15

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class ETFMonitor:
    def __init__(self):
        self.client = NSEClient()
        
    def get_high_volume_etfs(self) -> list[str]:
        logger.info("Fetching Master ETF List...")
        url = "https://www.nseindia.com/api/etf"
        
        data = self.client._request_with_retry(url)
        if not data:
            raise Exception("Failed to fetch Master ETF List from NSE.")
            
        etf_list = data.get('data', [])
        filtered_list = []
        for item in etf_list:
            symbol = item.get('symbol')
            vol_raw = item.get('qty') or item.get('totalTradedVolume', 0)
            try:
                volume = float(str(vol_raw).replace(',', ''))
            except Exception:
                volume = 0
                
            if volume >= MIN_VOLUME:
                if symbol:
                    filtered_list.append(symbol)
                    
        logger.info(f"📉 Total ETFs found: {len(etf_list)}")
        logger.info(f"🔥 High Volume ETFs (> {MIN_VOLUME}): {len(filtered_list)}")
        return filtered_list

    def check_etf_inav(self, symbol: str):
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
        params = {
            "functionName": "getSymbolData",
            "marketType": "N",
            "series": "EQ",
            "symbol": symbol
        }
        
        # Referer header is sometimes required by NSE for symbol data
        if self.client.mode == "curl_cffi" and self.client.session:
            self.client.session.headers["Referer"] = f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}"
            
        data = self.client._request_with_retry(url, params=params)
        
        if not data:
            logger.warning(f"   ⚠️ {symbol}: Failed to get quote data.")
            return
            
        equity_response = data.get('equityResponse', [])
        if not equity_response:
            logger.warning(f"   ⚠️ {symbol}: No equityResponse data found.")
            return
            
        main_data = equity_response[0]
        price_info = main_data.get('priceInfo', {})
        trade_info = main_data.get('tradeInfo', {})
        
        ltp = trade_info.get('lastPrice')
        inav = price_info.get('inav')
        
        if ltp and inav:
            try:
                ltp = float(str(ltp).replace(',', '').strip())
                inav = float(str(inav).replace(',', '').strip())
                if ltp == 0:
                    return
                diff = inav - ltp
                percent = (diff / ltp) * 100
                logger.info(f"   🔎 {symbol}: iNAV {inav} | LTP {ltp} (Gap: {percent:.2f}%)")
                
                if percent >= MIN_PROFIT_PERCENT:
                    logger.info(f"🚨 Arbitrage Opportunity detected for {symbol}!")
                    discord_notifier.send_etf_arbitrage_alert(
                        symbol=symbol,
                        inav=inav,
                        ltp=ltp,
                        percent_gap=percent
                    )
            except Exception as e:
                logger.error(f"   ⚠️ {symbol}: Error parsing price data - {e}")
        else:
            logger.warning(f"   ⚠️ {symbol}: Data missing (LTP: {ltp}, iNAV: {inav})")

    def run(self):
        try:
            if not self.client.initialize_session():
                raise Exception("Failed to initialize NSE session.")
                
            symbols = self.get_high_volume_etfs()
            
            if not symbols:
                logger.info(f"No ETFs found with volume > {MIN_VOLUME}. Exiting.")
                return
                
            logger.info(f"🚀 Starting checks on {len(symbols)} symbols...")
            
            for i, symbol in enumerate(symbols):
                if i > 0 and i % SESSION_REFRESH_EVERY == 0:
                    logger.info(f"\n🍪 Refreshing session at symbol {i+1}/{len(symbols)}...")
                    # Close old and initialize new to clear up potential memory leaks / dead sessions
                    self.client.close()
                    time.sleep(2)
                    self.client.initialize_session()
                    
                self.check_etf_inav(symbol)
                
                delay = DELAY_BETWEEN_CHECKS + random.uniform(-2, 5)
                logger.info(f"   ... Waiting {delay:.1f}s ({i+1}/{len(symbols)}) ...")
                time.sleep(delay)
                
            logger.info("✅ Run Complete.")
            
        finally:
            self.client.close()

if __name__ == "__main__":
    logger.info("--- ETF Monitor Script Started ---")
    try:
        monitor = ETFMonitor()
        monitor.run()
        logger.info("--- ETF Monitor Script Finished ---")
    except Exception as e:
        error_msg = str(e)
        tb = traceback.format_exc()
        logger.error(f"CRITICAL CRASH: {error_msg}\n{tb}")
        discord_notifier.send_etf_error_alert(
            error_message=error_msg,
            details=tb
        )
        sys.exit(1)
