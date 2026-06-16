#!/usr/bin/env python3
"""
Kevin Self-Hosted Server v1.0
Serves the Market Pulse Dashboard + JSON API endpoints.
No external dependencies, no API keys, 100% self-serviceable.

Usage:
    python3 scripts/self-hosted-server.py
    # Open http://localhost:8787 in browser
    # API: http://localhost:8787/api/market
    # Health: http://localhost:8787/health
"""

import os, json, urllib.request, http.server, time, datetime, threading

PORT = 8787
CACHE_TTL = 60  # seconds

# Find dashboard file
DASHBOARD_PATH = None
for p in [
    'market-pulse-dashboard.html',
    '/workspace/market-pulse-dashboard.html',
    '/srv/agents/workspaces/market-pulse-dashboard.html',
]:
    if os.path.exists(p):
        DASHBOARD_PATH = os.path.abspath(p)
        break

if not DASHBOARD_PATH:
    # Create a minimal dashboard inline
    DASHBOARD_HTML = None
else:
    with open(DASHBOARD_PATH) as f:
        DASHBOARD_HTML = f.read()

# In-memory cache
cache = {}
cache_lock = threading.Lock()

def fetch_json(url, timeout=10):
    try:
        data = urllib.request.urlopen(url, timeout=timeout).read()
        return json.loads(data)
    except Exception as e:
        return {"error": str(e)}

def get_briefing():
    """Load the latest generated briefing from briefings/ directory."""
    now = time.time()
    with cache_lock:
        if 'briefing' in cache and now - cache['briefing']['ts'] < CACHE_TTL * 5:
            return cache['briefing']['data']
    
    result = {
        'error': 'No briefing found',
        'briefing_dirs_checked': []
    }
    
    # Look in briefings/
    briefing_dir = '/workspace/briefings'
    for d in [briefing_dir, '/srv/agents/workspaces/briefings', 'briefings', '/workspace/reports']:
        result['briefing_dirs_checked'].append(d)
        if os.path.isdir(d):
            files = sorted([f for f in os.listdir(d) if f.endswith('.md')], reverse=True)
            if files:
                latest = files[0]
                path = os.path.join(d, latest)
                try:
                    with open(path) as f:
                        text = f.read()
                    result = {
                        'file': latest,
                        'generated_at': latest.replace('briefing-', '').replace('.md', '').replace('-', 'T') + 'Z',
                        'path': path,
                        'word_count': len(text.split()),
                        'char_count': len(text),
                        'preview': text[:2000],
                        'full_path': path
                    }
                except Exception as e:
                    result = {'error': f'Failed to read {path}: {e}'}
                break
    
    with cache_lock:
        cache['briefing'] = {'data': result, 'ts': now}
    return result


def get_regime():
    """Compute market regime analysis from current market data."""
    now = time.time()
    with cache_lock:
        if 'regime' in cache and now - cache['regime']['ts'] < CACHE_TTL * 5:
            return cache['regime']['data']
    
    market = get_market_data()
    result = {
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
        'signals': [],
        'total_score': 0,
        'regime': 'NEUTRAL'
    }
    
    fng = market.get('fear_greed', {})
    coins = market.get('coins', [])
    
    # Fear & Greed signal
    fng_val = fng.get('value', 50)
    if fng_val <= 25:
        result['signals'].append({
            'name': 'Fear & Greed',
            'value': fng_val,
            'score': 25,
            'signal': 'STRONG_BULLISH',
            'reason': f'Extreme fear ({fng_val}/100) - contrarian buy zone'
        })
        result['total_score'] += 25
    elif fng_val <= 45:
        result['signals'].append({
            'name': 'Fear & Greed',
            'value': fng_val,
            'score': 15,
            'signal': 'BULLISH',
            'reason': f'Fear zone ({fng_val}/100)'
        })
        result['total_score'] += 15
    elif fng_val >= 75:
        result['signals'].append({
            'name': 'Fear & Greed',
            'value': fng_val,
            'score': -15,
            'signal': 'BEARISH',
            'reason': f'Greed zone ({fng_val}/100) - potential top'
        })
        result['total_score'] -= 15
    
    # Price action signal
    if coins:
        btc = next((c for c in coins if c.get('symbol') == 'BITCOIN' or c.get('name') == 'BTC'), None)
        if btc:
            change = btc.get('change_24h', 0)
            if change > 3:
                result['signals'].append({'name': 'BTC 24h', 'value': f'{change:+.2f}%', 'score': 15, 'signal': 'BULLISH', 'reason': 'Strong upward momentum'})
                result['total_score'] += 15
            elif change > 0:
                result['signals'].append({'name': 'BTC 24h', 'value': f'{change:+.2f}%', 'score': 5, 'signal': 'MILD_BULLISH', 'reason': 'Slight upward movement'})
                result['total_score'] += 5
            elif change > -3:
                result['signals'].append({'name': 'BTC 24h', 'value': f'{change:+.2f}%', 'score': -5, 'signal': 'MILD_BEARISH', 'reason': 'Slight downward movement'})
                result['total_score'] -= 5
            else:
                result['signals'].append({'name': 'BTC 24h', 'value': f'{change:+.2f}%', 'score': -15, 'signal': 'BEARISH', 'reason': 'Strong downward momentum'})
                result['total_score'] -= 15
    
    # Determine regime
    if result['total_score'] >= 20:
        result['regime'] = 'ACCUMULATE'
    elif result['total_score'] >= 10:
        result['regime'] = 'BULLISH'
    elif result['total_score'] <= -20:
        result['regime'] = 'AVOID'
    elif result['total_score'] <= -10:
        result['regime'] = 'BEARISH'
    else:
        result['regime'] = 'NEUTRAL'
    
    result['fear_greed'] = {'value': fng_val, 'classification': fng.get('classification', '')} if fng else None
    result['btc_price'] = coins[0].get('price_usd', 0) if coins else None
    
    with cache_lock:
        cache['regime'] = {'data': result, 'ts': now}
    return result


def get_market_data():
    now = time.time()
    with cache_lock:
        if 'market' in cache and now - cache['market']['ts'] < CACHE_TTL:
            return cache['market']['data']
    
    result = {}
    
    # Crypto prices
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,cardano,chainlink,dogecoin,polkadot,avalanche-2&vs_currencies=usd&include_24hr_change=true'
    data = fetch_json(url)
    if 'error' not in data:
        coins = []
        for coin_id, info in data.items():
            name = coin_id.replace('-2', '').upper()
            coins.append({
                'name': name,
                'symbol': coin_id.split('-')[0].upper(),
                'price_usd': info.get('usd', 0),
                'change_24h': info.get('usd_24h_change', 0)
            })
        result['coins'] = sorted(coins, key=lambda c: c.get('price_usd', 0), reverse=True)
    
    # Global market data
    gdata = fetch_json('https://api.coingecko.com/api/v3/global', timeout=10)
    if 'error' not in gdata:
        g = gdata.get('data', {})
        result['global'] = {
            'market_cap_usd': g.get('total_market_cap', {}).get('usd', 0),
            'btc_dominance': g.get('market_cap_percentage', {}).get('btc', 0),
            'active_cryptos': g.get('active_cryptocurrencies', 0),
            'volume_24h_usd': g.get('total_volume', {}).get('usd', 0)
        }
    
    # Fear & Greed
    fng = fetch_json('https://api.alternative.me/fng/?limit=1')
    if 'error' not in fng and 'data' in fng:
        result['fear_greed'] = {
            'value': int(fng['data'][0].get('value', 50)),
            'classification': fng['data'][0].get('value_classification', 'Neutral')
        }
    
    # Trending coins
    trend = fetch_json('https://api.coingecko.com/api/v3/search/trending')
    if 'error' not in trend and 'coins' in trend:
        trending = []
        for c in trend['coins'][:10]:
            item = c.get('item', {})
            trending.append({
                'name': item.get('name', '?'),
                'symbol': item.get('symbol', '?'),
                'price_usd': item.get('price_btc', 0) * result.get('coins', [{}])[0].get('price_usd', 65000) / 1 if result.get('coins') else 0,
                'rank': item.get('market_cap_rank', 0)
            })
        result['trending'] = trending
    
    result['timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
    
    with cache_lock:
        cache['market'] = {'data': result, 'ts': now}
    
    return result

class KevinHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'service': 'kevin-market-pulse',
                'version': '1.0',
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'uptime': int(time.time() - server_start)
            }).encode())
            
        elif self.path == '/api/market':
            data = get_market_data()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            
        elif self.path == '/api/briefing':
            data = get_briefing()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            
        elif self.path == '/api/regime':
            data = get_regime()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            
        elif self.path == '/api':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'service': 'Kevin Market Pulse API',
                'version': '2.0',
                'endpoints': [
                    {'path': '/health', 'description': 'Health check'},
                    {'path': '/api', 'description': 'API listing'},
                    {'path': '/api/market', 'description': 'Crypto prices, global data, fear & greed, trending coins'},
                    {'path': '/api/briefing', 'description': 'Latest daily market briefing'},
                    {'path': '/api/regime', 'description': 'Market regime analysis'},
                ],
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }).encode())
            
        elif self.path == '/':
            if DASHBOARD_HTML:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(DASHBOARD_HTML.encode())
            else:
                # Generate a minimal dashboard inline
                data = get_market_data()
                html = generate_minimal_dashboard(data)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'not found', 'available': ['/', '/health', '/api', '/api/market', '/api/briefing', '/api/regime']}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {args[0]} {args[1]} {args[2]}")

def generate_minimal_dashboard(data):
    """Generate a simple HTML dashboard if the saved one isn't available."""
    coins_html = ''
    for c in data.get('coins', []):
        p = c.get('price_usd', 0)
        ch = c.get('change_24h', 0)
        icon = '🟢' if ch >= 0 else '🔴'
        cls = 'green' if ch >= 0 else 'red'
        coins_html += f'''
        <div class="card">
            <div class="coin-name">{c['name']}</div>
            <div class="coin-price">${p:,.2f}</div>
            <div class="coin-change {cls}">{icon} {ch:+.2f}%</div>
        </div>'''
    
    fg = data.get('fear_greed', {})
    fg_html = f'''
        <div class="card">
            <div class="coin-name">Fear & Greed</div>
            <div class="coin-price" style="font-size:2.5rem">{fg.get('value', '?')}/100</div>
            <div class="coin-change">{fg.get('classification', 'N/A')}</div>
        </div>''' if fg else ''
    
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Kevin Market Pulse</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px;max-width:1200px;margin:0 auto;}}
h1{{font-size:1.6rem;margin-bottom:4px;}}
.subtitle{{color:#8b949e;font-size:0.85rem;margin-bottom:20px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;}}
.coin-name{{color:#8b949e;font-size:0.85rem;margin-bottom:4px;}}
.coin-price{{font-size:1.3rem;font-weight:600;}}
.coin-change{{font-size:0.95rem;margin-top:4px;}}
.green{{color:#3fb950;}}.red{{color:#f85149;}}
.update{{color:#8b949e;font-size:0.75rem;margin-top:20px;text-align:center;}}
</style></head><body>
<h1>📊 Kevin Market Pulse</h1>
<p class="subtitle">Self-hosted · Live data from CoinGecko · Updated every {CACHE_TTL}s</p>
<div class="grid">
{coins_html}
{fg_html}
</div>
<p class="update">Last updated: {data.get('timestamp', 'N/A')}</p>
<script>setTimeout(()=>location.reload(),60000)</script>
</body></html>'''

server_start = time.time()

def run_server():
    server = http.server.HTTPServer(('0.0.0.0', PORT), KevinHTTPHandler)
    print(f"🚀 Kevin Market Pulse Server running on http://0.0.0.0:{PORT}")
    print(f"   Dashboard:  http://localhost:{PORT}/")
    print(f"   API:        http://localhost:{PORT}/api/market")
    print(f"   Health:     http://localhost:{PORT}/health")
    print(f"   Ready for reverse proxy or direct use.")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
