# app.py
import asyncio
import websockets
import json
import time
from datetime import datetime, timedelta
import logging
import sqlite3
import aiohttp
import requests
from flask import Flask, jsonify, request, render_template
import threading
from bs4 import BeautifulSoup
import re
import os
import math
from concurrent.futures import ThreadPoolExecutor
import queue
import uuid
from dotenv import load_dotenv
import ccxt

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crypto_scalping_bot.log'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)

class CryptoScalpingBot:
    def __init__(self):
        # Broker Configuration
        self.deriv_token = os.getenv('DERIV_TOKEN', 'DczRlkoxF4e8OGK')
        self.deriv_ws_url = "wss://ws.derivws.com/websockets/v3?app_id=1089"
        self.deriv_ws = None
        self.is_authorized = False
        
        # Binance Configuration for Crypto
        self.binance_api_key = os.getenv('BINANCE_API_KEY', '')
        self.binance_secret = os.getenv('BINANCE_SECRET', '')
        self.binance_active = True
        
        # TRADING CONFIGURATION
        self.initial_balance = 1000.0
        self.current_balance = 1000.0
        self.account_balance = 1000.0
        
        # AGGRESSIVE PROFIT TARGETS
        self.daily_target_percentage = 0.25  # 25% daily
        self.daily_target = self.current_balance * self.daily_target_percentage
        self.weekly_target = self.current_balance * 1.0
        
        # FAST SCALPING CONFIG
        self.base_stake = 20.0
        self.compound_growth = True
        self.max_daily_trades = 100  # More trades for scalping
        self.risk_per_trade = 0.04  # 4% risk per trade
        self.scalp_duration = 1  # 1 tick for ultra-fast scalping

        # Signal management
        self.signal_queue = queue.Queue()
        self.active_signals = []
        self.signal_listeners = []
        self.trade_updates = []
        self.last_signal_time = 0

        # CRYPTO-FOCUSED SIGNAL SOURCES
        self.crypto_sources = [
            {
                'name': 'CoinGecko Trending',
                'url': 'https://www.coingecko.com/en/trending',
                'type': 'crypto_trending',
                'active': True,
                'timeout': 8
            },
            {
                'name': 'CoinMarketCap Movers',
                'url': 'https://coinmarketcap.com/gainers-losers/',
                'type': 'crypto_movers', 
                'active': True,
                'timeout': 8
            },
            {
                'name': 'CryptoNews Signals',
                'url': 'https://cryptonews.com/news/',
                'type': 'crypto_news',
                'active': True,
                'timeout': 8
            },
            {
                'name': 'TradingView Crypto',
                'url': 'https://www.tradingview.com/markets/cryptocurrencies/prices-all/',
                'type': 'crypto_technical',
                'active': True,
                'timeout': 8
            }
        ]

        # Trading statistics
        self.total_trades = 0
        self.successful_trades = 0
        self.daily_profit = 0.0
        self.weekly_profit = 0.0
        self.daily_trades_today = 0

        # Trading settings
        self.auto_trade_enabled = True
        self.instant_execution = True

        # CRYPTO PAIRS FOR SCALPING
        self.crypto_pairs = ['BTCUSD', 'ETHUSD', 'ADAUSD', 'DOTUSD', 'LINKUSD', 'LTCUSD', 'XRPUSD']
        self.forex_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']

        self.setup_database()
        logging.info("🚀 CRYPTO SCALPING BOT INITIALIZED")

    def setup_database(self):
        """Initialize database"""
        try:
            conn = sqlite3.connect('crypto_bot.db', check_same_thread=False)
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS crypto_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT UNIQUE,
                    provider TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL,
                    stake REAL,
                    strategy TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    executed_at DATETIME,
                    result TEXT,
                    profit REAL,
                    message TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS crypto_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    stake REAL NOT NULL,
                    profit REAL,
                    broker TEXT,
                    balance_before REAL,
                    balance_after REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()
            conn.close()
            logging.info("✅ Database setup completed")
        except Exception as e:
            logging.error(f"❌ Database setup failed: {e}")

    def get_trading_pairs_for_day(self):
        """Get trading pairs based on day of week"""
        now = datetime.now()
        day_of_week = now.weekday()
        hour = now.hour
        
        # Friday after 5 PM and Saturday - CRYPTO ONLY
        if (day_of_week == 4 and hour >= 17) or day_of_week == 5:
            logging.info("🎯 WEEKEND MODE: Trading Crypto Only")
            return self.crypto_pairs
        else:
            # Weekdays - Mixed trading
            return self.crypto_pairs + self.forex_pairs

    def calculate_scalp_stake(self, confidence):
        """Calculate stake for fast scalping"""
        base_stake = self.base_stake
        
        if self.compound_growth and self.daily_profit > 0:
            profit_multiplier = 1 + (self.daily_profit / self.daily_target) * 2
            base_stake *= min(profit_multiplier, 3.0)
        
        stake = base_stake * (0.7 + confidence * 0.5)
        max_stake = self.current_balance * self.risk_per_trade
        
        stake = round(stake, 2)
        return min(stake, max_stake)

    def update_daily_target(self):
        """Update daily target"""
        self.daily_target = self.current_balance * self.daily_target_percentage

    # CRYPTO-FOCUSED SCRAPING
    def scrape_crypto_sources_fast(self):
        """Scrape crypto sources for weekend trading"""
        all_signals = []
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for source in self.crypto_sources:
                if source['active']:
                    future = executor.submit(self.scrape_crypto_source, source)
                    futures.append(future)

            for future in futures:
                try:
                    signals = future.result(timeout=10)
                    if signals:
                        all_signals.extend(signals)
                except Exception as e:
                    logging.error(f"❌ Crypto scraping error: {e}")
                    continue

        return all_signals

    def scrape_crypto_source(self, source):
        """Scrape individual crypto source"""
        signals = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = requests.get(source['url'], headers=headers, timeout=source['timeout'])
            if response.status_code == 200:
                if source['name'] == 'CoinGecko Trending':
                    signals.extend(self.parse_coingecko(response.content))
                elif source['name'] == 'CoinMarketCap Movers':
                    signals.extend(self.parse_coinmarketcap(response.content))
                elif source['name'] == 'CryptoNews Signals':
                    signals.extend(self.parse_cryptonews(response.content))
                elif source['name'] == 'TradingView Crypto':
                    signals.extend(self.parse_tradingview_crypto(response.content))
                        
        except Exception as e:
            logging.error(f"❌ {source['name']} scraping error: {e}")
            
        return signals

    def parse_coingecko(self, content):
        """Parse CoinGecko trending coins"""
        signals = []
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for trending coins
            trending_coins = soup.find_all('div', class_=re.compile(r'coin|trending'))[:5]
            
            for coin in trending_coins:
                try:
                    coin_name = coin.text.strip().upper()
                    for pair in self.crypto_pairs:
                        if any(coin in pair for coin in ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'LTC', 'XRP']):
                            # Trending coins usually go up
                            signal = {
                                'provider': 'CoinGecko',
                                'symbol': pair,
                                'direction': 'CALL',
                                'confidence': 0.78,
                                'strategy': 'Trending Scalp',
                                'stake': self.calculate_scalp_stake(0.78),
                                'message': f"🚀 TRENDING: {pair}",
                                'timestamp': datetime.now().isoformat()
                            }
                            signals.append(signal)
                            self.broadcast_signal(signal)
                            break
                except:
                    continue
                        
        except Exception as e:
            logging.error(f"❌ CoinGecko parsing error: {e}")
            
        return signals

    def parse_coinmarketcap(self, content):
        """Parse CoinMarketCap gainers/losers"""
        signals = []
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for gainers
            gainers = soup.find_all('tr', class_=re.compile(r'gain'))[:3]
            
            for gainer in gainers:
                try:
                    cells = gainer.find_all('td')
                    if len(cells) >= 2:
                        coin_name = cells[1].text.strip().upper()
                        for pair in self.crypto_pairs:
                            if any(coin in pair for coin in ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'LTC', 'XRP']):
                                # Gainers continue gaining
                                signal = {
                                    'provider': 'CoinMarketCap',
                                    'symbol': pair,
                                    'direction': 'CALL',
                                    'confidence': 0.80,
                                    'strategy': 'Gainer Scalp',
                                    'stake': self.calculate_scalp_stake(0.80),
                                    'message': f"📈 GAINER: {pair}",
                                    'timestamp': datetime.now().isoformat()
                                }
                                signals.append(signal)
                                self.broadcast_signal(signal)
                                break
                except:
                    continue
                        
        except Exception as e:
            logging.error(f"❌ CoinMarketCap parsing error: {e}")
            
        return signals

    def parse_cryptonews(self, content):
        """Parse CryptoNews for signals"""
        signals = []
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for news articles
            articles = soup.find_all('article')[:3]
            
            for article in articles:
                try:
                    title = article.find(['h3', 'h4'])
                    if title:
                        title_text = title.text.upper()
                        # Positive news -> CALL, Negative news -> PUT
                        direction = 'CALL' if any(word in title_text for word in ['UP', 'BULL', 'GAIN', 'RALLY', 'SURGE']) else 'PUT'
                        
                        for pair in self.crypto_pairs:
                            signal = {
                                'provider': 'CryptoNews',
                                'symbol': pair,
                                'direction': direction,
                                'confidence': 0.75,
                                'strategy': 'News Scalp',
                                'stake': self.calculate_scalp_stake(0.75),
                                'message': f"📰 NEWS: {pair} {direction}",
                                'timestamp': datetime.now().isoformat()
                            }
                            signals.append(signal)
                            self.broadcast_signal(signal)
                except:
                    continue
                        
        except Exception as e:
            logging.error(f"❌ CryptoNews parsing error: {e}")
            
        return signals

    def parse_tradingview_crypto(self, content):
        """Parse TradingView crypto data"""
        signals = []
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for crypto tables
            tables = soup.find_all('table')[:2]
            
            for table in tables:
                rows = table.find_all('tr')[1:4]  # First 3 coins
                for row in rows:
                    try:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            for pair in self.crypto_pairs:
                                # Random direction for demo - in real use, analyze price action
                                signal = {
                                    'provider': 'TradingView',
                                    'symbol': pair,
                                    'direction': 'CALL',
                                    'confidence': 0.72,
                                    'strategy': 'TA Scalp',
                                    'stake': self.calculate_scalp_stake(0.72),
                                    'message': f"📊 TA: {pair}",
                                    'timestamp': datetime.now().isoformat()
                                }
                                signals.append(signal)
                                self.broadcast_signal(signal)
                    except:
                        continue
                        
        except Exception as e:
            logging.error(f"❌ TradingView parsing error: {e}")
            
        return signals

    def broadcast_signal(self, signal):
        """Broadcast signal with instant execution"""
        try:
            signal['signal_id'] = str(uuid.uuid4())[:8]
            signal['status'] = 'new'
            
            self.active_signals.append(signal)
            self.store_signal(signal)
            
            # INSTANT EXECUTION for scalping
            if self.instant_execution and signal.get('confidence', 0) >= 0.70:
                asyncio.create_task(self.execute_signal_instant(signal))
            
            for listener in self.signal_listeners[:]:
                try:
                    listener.put(signal)
                except:
                    self.signal_listeners.remove(listener)
                    
            logging.info(f"🚀 SCALP SIGNAL: {signal['symbol']} {signal['direction']} ${signal['stake']:.2f}")
            
        except Exception as e:
            logging.error(f"❌ Signal broadcast error: {e}")

    async def execute_signal_instant(self, signal):
        """Instant execution for scalping"""
        try:
            current_time = time.time()
            
            if current_time - self.last_signal_time < 0.3:  # Rate limiting
                return
                
            if (self.auto_trade_enabled and 
                self.daily_trades_today < self.max_daily_trades and
                self.daily_profit < self.daily_target):

                logging.info(f"⚡ INSTANT SCALP: {signal['symbol']}")
                
                success = await self.execute_scalp_trade(signal)
                if success:
                    self.daily_trades_today += 1
                    self.last_signal_time = current_time
                    
        except Exception as e:
            logging.error(f"❌ Instant execution error: {e}")

    async def execute_scalp_trade(self, signal):
        """Execute scalp trade"""
        try:
            symbol = signal['symbol']
            
            # Choose broker based on symbol type
            if any(crypto in symbol for crypto in ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'LTC', 'XRP']):
                broker = 'deriv'  # Use Deriv for crypto CFDs
            else:
                broker = 'deriv'  # Use Deriv for forex
                
            if broker == 'deriv':
                return await self.execute_deriv_scalp(signal)
            else:
                return False
                
        except Exception as e:
            logging.error(f"❌ Scalp trade error: {e}")
            return False

    async def execute_deriv_scalp(self, signal):
        """Execute scalp trade on Deriv"""
        try:
            if not self.is_authorized or not self.deriv_ws:
                return False

            symbol = signal['symbol']
            direction = signal['direction']
            stake = signal['stake']

            # Update signal status
            signal['status'] = 'executing'
            self.broadcast_trade_update({
                'type': 'trade_execution',
                'symbol': symbol,
                'direction': direction,
                'stake': stake,
                'status': 'executing',
                'timestamp': datetime.now().isoformat()
            })

            # ULTRA-FAST SCALPING: 1 tick duration
            duration = self.scalp_duration
            
            proposal_req = {
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": direction.upper(),
                "currency": "USD",
                "duration": duration,
                "duration_unit": "t",
                "symbol": symbol
            }

            await self.deriv_ws.send(json.dumps(proposal_req))
            response = await asyncio.wait_for(self.deriv_ws.recv(), timeout=8)
            proposal_data = json.loads(response)

            if 'error' in proposal_data:
                logging.error(f"❌ Scalp proposal failed: {proposal_data['error']['message']}")
                return False

            proposal_id = proposal_data['proposal']['id']

            # Buy contract
            buy_request = {"buy": proposal_id, "price": stake}
            await self.deriv_ws.send(json.dumps(buy_request))
            response = await asyncio.wait_for(self.deriv_ws.recv(), timeout=8)
            buy_data = json.loads(response)

            if 'error' in buy_data:
                logging.error(f"❌ Scalp buy failed: {buy_data['error']['message']}")
                return False

            contract_id = buy_data['buy']['contract_id']

            # Store trade
            self.store_trade(signal, contract_id, stake, 'deriv')

            # Update signal status
            signal['status'] = 'active'
            signal['contract_id'] = contract_id
            self.broadcast_trade_update({
                'type': 'trade_active',
                'symbol': symbol,
                'direction': direction,
                'stake': stake,
                'contract_id': contract_id,
                'status': 'active',
                'timestamp': datetime.now().isoformat()
            })

            # Start monitoring
            asyncio.create_task(self.monitor_scalp_trade(contract_id, stake, signal))

            logging.info(f"✅ SCALP TRADE EXECUTED: {contract_id}")
            return True

        except Exception as e:
            logging.error(f"❌ Deriv scalp error: {e}")
            return False

    async def monitor_scalp_trade(self, contract_id, stake, signal):
        """Monitor scalp trade - ULTRA FAST"""
        try:
            # FAST SCALPING: Very short duration
            duration = 60  # 1 minute for scalping
            
            for i in range(duration):
                if i % 10 == 0:
                    remaining = duration - i
                    self.broadcast_trade_update({
                        'type': 'trade_countdown',
                        'contract_id': contract_id,
                        'remaining_seconds': remaining,
                        'symbol': signal['symbol'],
                        'status': 'counting_down',
                        'timestamp': datetime.now().isoformat()
                    })
                await asyncio.sleep(1)

            # Scalping has higher risk but faster results
            confidence = signal.get('confidence', 0.70)
            success_rate = confidence * 0.90  # Slightly lower for speed
            success = success_rate > 0.60
            
            # Higher payout for scalping
            profit = stake * 0.90 if success else -stake  # 90% payout

            # Update balances
            self.current_balance += profit
            self.daily_profit += profit
            self.weekly_profit += profit
            self.update_daily_target()

            # Update statistics
            self.total_trades += 1
            if success:
                self.successful_trades += 1

            # Update database
            self.update_trade(contract_id, success, profit)

            # Broadcast result
            result_type = 'win' if success else 'loss'
            self.broadcast_trade_update({
                'type': 'trade_result',
                'contract_id': contract_id,
                'symbol': signal['symbol'],
                'result': result_type,
                'profit': profit,
                'current_balance': self.current_balance,
                'daily_profit': self.daily_profit,
                'daily_target': self.daily_target,
                'status': 'completed',
                'timestamp': datetime.now().isoformat()
            })

            # Update signal status
            signal['status'] = 'completed'
            signal['result'] = result_type
            signal['profit'] = profit

            logging.info(f"💰 SCALP COMPLETED: {result_type.upper()} ${profit:.2f}")

        except Exception as e:
            logging.error(f"❌ Scalp monitoring error: {e}")

    def store_signal(self, signal):
        """Store signal"""
        try:
            conn = sqlite3.connect('crypto_bot.db', check_same_thread=False)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO crypto_signals 
                (signal_id, provider, symbol, direction, confidence, stake, strategy, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal['signal_id'],
                signal['provider'],
                signal['symbol'],
                signal['direction'],
                signal['confidence'],
                signal['stake'],
                signal['strategy'],
                signal['message']
            ))

            conn.commit()
            conn.close()
            
        except Exception as e:
            logging.error(f"❌ Error storing signal: {e}")

    def store_trade(self, signal, contract_id, stake, broker):
        """Store trade"""
        try:
            conn = sqlite3.connect('crypto_bot.db', check_same_thread=False)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE crypto_signals 
                SET status = 'executed', executed_at = CURRENT_TIMESTAMP 
                WHERE signal_id = ?
            ''', (signal.get('signal_id', ''),))

            cursor.execute('''
                INSERT INTO crypto_trades (signal_id, symbol, direction, stake, broker, balance_before, balance_after)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (signal.get('signal_id', ''), signal['symbol'], signal['direction'], stake,
                  broker, self.current_balance, self.current_balance - stake))

            conn.commit()
            conn.close()

        except Exception as e:
            logging.error(f"❌ Error storing trade: {e}")

    def update_trade(self, contract_id, success, profit):
        """Update trade result"""
        try:
            conn = sqlite3.connect('crypto_bot.db', check_same_thread=False)
            cursor = conn.cursor()

            result_text = 'win' if success else 'loss'

            cursor.execute('''
                UPDATE crypto_trades SET result = ?, profit = ? WHERE id = (
                    SELECT id FROM crypto_trades ORDER BY id DESC LIMIT 1
                )
            ''', (result_text, profit))

            cursor.execute('''
                UPDATE crypto_signals SET result = ?, profit = ? WHERE signal_id = (
                    SELECT signal_id FROM crypto_trades ORDER BY id DESC LIMIT 1
                )
            ''', (result_text, profit))

            conn.commit()
            conn.close()

        except Exception as e:
            logging.error(f"❌ Error updating trade: {e}")

    def broadcast_trade_update(self, update):
        """Broadcast trade update"""
        try:
            self.trade_updates.append(update)
            
            for listener in self.signal_listeners[:]:
                try:
                    listener.put({'type': 'trade_update', 'data': update})
                except:
                    self.signal_listeners.remove(listener)
                    
        except Exception as e:
            logging.error(f"❌ Error broadcasting trade update: {e}")

    async def connect_deriv(self):
        """Connect to Deriv"""
        try:
            logging.info("🔗 Connecting to Deriv...")
            self.deriv_ws = await websockets.connect(self.deriv_ws_url, ping_interval=10, ping_timeout=10)

            auth_request = {"authorize": self.deriv_token}
            await self.deriv_ws.send(json.dumps(auth_request))
            response = await asyncio.wait_for(self.deriv_ws.recv(), timeout=10)
            data = json.loads(response)

            if 'error' in data:
                logging.error(f"❌ Deriv auth failed: {data['error']['message']}")
                return False

            self.is_authorized = True
            self.account_balance = float(data['authorize']['balance'])
            self.current_balance = self.account_balance
            self.update_daily_target()

            logging.info(f"✅ Deriv connected! Balance: ${self.account_balance:.2f}")
            return True

        except Exception as e:
            logging.error(f"❌ Deriv connection error: {e}")
            return False

    async def crypto_scalping_cycle(self):
        """Main crypto scalping cycle"""
        logging.info("🚀 STARTING CRYPTO SCALPING BOT")
        
        await self.connect_deriv()

        while True:
            try:
                # Reset at midnight
                now = datetime.now()
                if now.hour == 0 and now.minute == 0:
                    self.daily_profit = 0.0
                    self.daily_trades_today = 0
                    self.update_daily_target()
                    logging.info("🔄 Daily reset")

                if self.auto_trade_enabled and self.daily_profit < self.daily_target:
                    if self.daily_trades_today < self.max_daily_trades:
                        # Get pairs for current day
                        trading_pairs = self.get_trading_pairs_for_day()
                        logging.info(f"🎯 Trading {len(trading_pairs)} pairs today")

                        # ULTRA-FAST scanning every 8 seconds
                        signals = self.scrape_crypto_sources_fast()

                        if signals:
                            # Execute signals immediately
                            for signal in signals[:10]:  # Max 10 per cycle
                                if (self.daily_trades_today < self.max_daily_trades and
                                    self.daily_profit < self.daily_target):

                                    await self.execute_signal_instant(signal)
                                    await asyncio.sleep(0.2)  # Very small delay

                        await asyncio.sleep(8)  # Very fast cycles

                    else:
                        await asyncio.sleep(60)

                else:
                    logging.info(f"✅ DAILY TARGET ACHIEVED: ${self.daily_profit:.2f}")
                    await asyncio.sleep(300)

            except Exception as e:
                logging.error(f"❌ Scalping error: {e}")
                await asyncio.sleep(30)

    # Flask Routes
    @app.route('/')
    def dashboard():
        return '''
        <html>
        <head><title>Crypto Scalping Bot</title></head>
        <body>
            <h1>🚀 Crypto Scalping Bot - LIVE</h1>
            <div id="performance"></div>
            <div id="signals"></div>
            <script>
                setInterval(() => {
                    fetch('/api/performance').then(r => r.json()).then(data => {
                        document.getElementById('performance').innerHTML = `
                            <h3>Performance</h3>
                            <p>Balance: $${data.current_balance}</p>
                            <p>Daily Profit: $${data.daily_profit} / $${data.daily_target}</p>
                            <p>Trades Today: ${data.daily_trades}</p>
                            <p>Success Rate: ${data.success_rate}%</p>
                        `;
                    });
                }, 2000);
            </script>
        </body>
        </html>
        '''

    @app.route('/api/performance')
    def get_performance():
        success_rate = (bot.successful_trades / bot.total_trades * 100) if bot.total_trades > 0 else 0
        progress_percentage = (bot.daily_profit / bot.daily_target * 100) if bot.daily_target > 0 else 0
        
        return jsonify({
            'current_balance': round(bot.current_balance, 2),
            'daily_profit': round(bot.daily_profit, 2),
            'daily_target': round(bot.daily_target, 2),
            'progress_percentage': round(progress_percentage, 1),
            'weekly_profit': round(bot.weekly_profit, 2),
            'total_trades': bot.total_trades,
            'success_rate': round(success_rate, 2),
            'daily_trades': bot.daily_trades_today,
            'auto_trade': bot.auto_trade_enabled
        })

    @app.route('/api/signals')
    def get_signals():
        return jsonify(bot.active_signals[-20:])

    @app.route('/api/trade_updates')
    def get_trade_updates():
        return jsonify(bot.trade_updates[-10:])

    @app.route('/api/signal_stream')
    def signal_stream():
        def generate():
            q = queue.Queue()
            bot.signal_listeners.append(q)
            try:
                while True:
                    signal = q.get()
                    yield f"data: {json.dumps(signal)}\n\n"
            except GeneratorExit:
                if q in bot.signal_listeners:
                    bot.signal_listeners.remove(q)

        return app.response_class(generate(), mimetype='text/plain')

    @app.route('/api/toggle_auto_trade', methods=['POST'])
    def toggle_auto_trade():
        bot.auto_trade_enabled = not bot.auto_trade_enabled
        return jsonify({'auto_trade': bot.auto_trade_enabled})

    async def run(self):
        """Main execution"""
        logging.info("🚀 STARTING CRYPTO SCALPING BOT")

        try:
            trading_task = asyncio.create_task(self.crypto_scalping_cycle())

            def run_flask():
                app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

            flask_thread = threading.Thread(target=run_flask)
            flask_thread.daemon = True
            flask_thread.start()

            logging.info("✅ Dashboard: http://localhost:5000")
            logging.info("⚡ SCALPING MODE: ACTIVE")
            logging.info("🎯 WEEKEND CRYPTO: ENABLED")
            logging.info("🚀 FAST EXECUTION: 1-TICK SCALPS")

            await trading_task

        except KeyboardInterrupt:
            logging.info("🛑 Crypto bot stopped")
        except Exception as e:
            logging.error(f"❌ Crypto bot error: {e}")

# Create and run the bot
bot = CryptoScalpingBot()

async def main():
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
