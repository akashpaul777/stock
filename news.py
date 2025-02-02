import requests
import time
import re

# API Key and Base URL
API_KEY = {'X-API-Key': 'II679A88'}  # Replace with your actual API key
API_URL = "http://localhost:9999/v1"

# Trading parameters
MAX_POSITION = 25000  # Maximum allowed position
INITIAL_ORDER_SIZE = 5000  # Initial maximum order size
TIME_LIMIT = 290  # Time near the session end when orders should be canceled
TRANSACTION_COST = 0.02  # Transaction cost per share

processed_news_ids = set()
# Tickers for PD3
TICKER_UB = 'UB'
TICKER_GEM = 'GEM'
TICKER_ETF = 'ETF'

# Track cumulative price estimates
price_estimates = {
    'UB': {'lowest': float('-inf'), 'highest': float('inf'), "pred": None},
    'GEM': {'lowest': float('-inf'), 'highest': float('inf'), "pred": None},
}


def get_open_orders(session):
    """Fetch all open orders."""
    response = session.get(f'{API_URL}/orders', params={'status': 'OPEN'})
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error fetching open orders: {response.status_code}")


def get_tick(session):
    resp = session.get(f'{API_URL}/case')
    if resp.ok:
        case = resp.json()
        return case['tick']
    raise Exception("Error fetching tick.")


def get_last_price(session, ticker):
    """Fetch the last traded price for the given stock symbol."""
    payload = {'ticker': ticker, 'limit': 1}
    response = session.get(f'{API_URL}/securities/history', params=payload)
    if response.status_code == 200:
        price_history = response.json()
        if price_history:
            return price_history[0]['close']  # Return the last close price
    else:
        raise Exception(f"Error fetching last price: {response.status_code}")


def get_news(session):
    """Fetch the latest news from the RIT API."""
    url = f'{API_URL}/news'
    response = session.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error fetching news: {response.status_code}")


def calculate_range(final_estimate, elapsed_seconds):
    """Calculate the possible price range based on elapsed time."""
    adjustment = (300 - elapsed_seconds) / 50
    highest_possible_price = final_estimate + adjustment
    lowest_possible_price = final_estimate - adjustment
    return lowest_possible_price, highest_possible_price


def update_price_estimates(ticker, final_estimate, elapsed_seconds):
    """Update the cumulative price estimate range by finding the overlap."""
    global price_estimates
    low, high = calculate_range(final_estimate, elapsed_seconds)
    price_estimates[ticker]['lowest'] = max(price_estimates[ticker]['lowest'], low)
    price_estimates[ticker]['highest'] = min(price_estimates[ticker]['highest'], high)
    price_estimates[ticker]["pred"] = final_estimate

    print(f"Updated range for {ticker}: Lowest = ${price_estimates[ticker]['lowest']:.2f}, Highest = ${price_estimates[ticker]['highest']:.2f}")


def extract_elapsed_time(news_body):
    """Extract elapsed time from news body."""
    match = re.search(r'After (\d+) seconds', news_body)
    if match:
        return int(match.group(1))
    return None  # Return None if no match is found


def process_news_item(news_item):
    """Process a single news item to update the price estimates."""
    ticker = None
    if "UB" in news_item['headline']:
        ticker = 'UB'
    elif "GEM" in news_item['headline']:
        ticker = 'GEM'

    if ticker:
        final_estimate = float(news_item['body'].split('$')[1])
        elapsed_seconds = extract_elapsed_time(news_item['body'])
        if elapsed_seconds is not None:
            update_price_estimates(ticker, final_estimate, elapsed_seconds)


def generate_signal(session, ticker):
    """Generate buy, sell, or hold signal for a given ticker based on the estimated range."""
    current_price = get_last_price(session, ticker)
    lowest_estimate = price_estimates[ticker]['lowest']
    highest_estimate = price_estimates[ticker]['highest']

    if current_price < lowest_estimate:
        return "BUY"
    elif current_price > highest_estimate:
        return "SELL"
    else:
        return "HOLD"


def generate_etf_arbitrage_signal(session):
    """Generate buy/sell signal for the ETF based on the combined estimated fair value of UB and GEM."""
    ub_price = get_last_price(session, 'UB')
    gem_price = get_last_price(session, 'GEM')
    etf_price = get_last_price(session, 'ETF')

    # Check if price estimates for both UB and GEM are available
    if price_estimates['UB']["pred"] is None or price_estimates['GEM']["pred"] is None:
        # If estimates are missing, skip the arbitrage check and return "HOLD"
        print("Insufficient data for arbitrage signal. Waiting for more news.")
        return "HOLD"

    # Combined fair value of UB and GEM based on their current estimates
    combined_estimate = price_estimates['UB']["pred"] + price_estimates['GEM']["pred"]

    if etf_price < combined_estimate:
        return "BUY ETF, SELL UB and GEM"
    elif etf_price > combined_estimate:
        return "SELL ETF, BUY UB and GEM"
    else:
        return "HOLD"


def execute_trade(session, signal, ticker):
    """Execute trade based on the signal for a specific ticker."""
    quantity = INITIAL_ORDER_SIZE
    price = get_last_price(session, ticker)
    if signal == "BUY":
        submit_order(session, ticker, price + TRANSACTION_COST, quantity, 'BUY')
    elif signal == "SELL":
        submit_order(session, ticker, price - TRANSACTION_COST, quantity, 'SELL')


def submit_order(session, ticker, price, quantity, side):
    """Submit a buy or sell order with transaction cost consideration."""
    quantity = min(quantity, 10000)  # Ensure order size does not exceed 10,000 shares
    payload = {
        'ticker': ticker,
        'type': 'LIMIT',
        'quantity': quantity,
        'action': side,
        'price': price
    }
    response = session.post(f'{API_URL}/orders', params=payload)
    return response.json()


def close_all_positions(session):
    """Close out all positions at session end based on final prices."""
    tickers = [TICKER_UB, TICKER_GEM, TICKER_ETF]
    for ticker in tickers:
        position = get_current_position(session, ticker)
        if position > 0:
            submit_order(session, ticker, get_last_price(session, ticker), position, 'SELL')
        elif position < 0:
            submit_order(session, ticker, get_last_price(session, ticker), abs(position), 'BUY')


def main():
    with requests.Session() as session:
        session.headers.update(API_KEY)
        tick = get_tick(session)

        while True:
            if tick >= TIME_LIMIT:
                close_all_positions(session)
                break

            news = get_news(session)
            for item in news:
                process_news_item(item)

            # Generate signals for each ticker
            ub_signal = generate_signal(session, 'UB')
            gem_signal = generate_signal(session, 'GEM')
            etf_signal = generate_etf_arbitrage_signal(session)

            # Execute trades based on signals
            execute_trade(session, ub_signal, 'UB')
            execute_trade(session, gem_signal, 'GEM')

            # Special case for ETF arbitrage
            if etf_signal == "BUY ETF, SELL UB and GEM":
                execute_trade(session, "BUY", TICKER_ETF)
                execute_trade(session, "SELL", TICKER_UB)
                execute_trade(session, "SELL", TICKER_GEM)
            elif etf_signal == "SELL ETF, BUY UB and GEM":
                execute_trade(session, "SELL", TICKER_ETF)
                execute_trade(session, "BUY", TICKER_UB)
                execute_trade(session, "BUY", TICKER_GEM)

            # Sleep briefly to avoid too frequent API calls
            time.sleep(1)
            tick = get_tick(session)


if __name__ == '__main__':
    main()
