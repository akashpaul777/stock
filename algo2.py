import requests
import time
import pandas as pd

# API Key and Base URL
API_KEY = {'X-API-Key': 'II679A88'}  # Replace with your actual API key
API_URL = "http://localhost:9999/v1"

# Trading parameters
SPREAD = 0.02  # Spread between buy and sell prices
MAX_ORDER_SIZE = 5000  # Maximum allowed order size
MAX_POSITION = 25000  # Maximum allowed position
TIME_LIMIT = 290  # Time near the session end when orders should be canceled

def get_open_orders(session):
    """Fetch all open orders."""
    response = session.get(f'{API_URL}/orders', params={'status': 'OPEN'}, headers=API_KEY)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error fetching open orders: {response.status_code}")

def fetch_price_history(session, ticker, limit=200):
    """Fetch the price history for the given stock ticker."""
    payload = {'ticker': ticker, 'limit': limit}
    response = session.get(f'{API_URL}/securities/history', params=payload, headers=API_KEY)
    if response.status_code == 200:
        price_history = response.json()
        return pd.DataFrame(price_history)  # Convert to DataFrame for easier calculation
    else:
        raise Exception(f"Error fetching price history: {response.status_code}")

def calculate_moving_average_and_low(prices_df, window=50):
    """Calculate the moving average and low price over a given window."""
    # Calculate moving average
    prices_df['moving_average'] = prices_df['close'].rolling(window=window).mean()
    
    # Calculate low price over the same window
    prices_df['low'] = prices_df['low'].rolling(window=window).min()
    
    # Get the most recent values of moving average and low price
    moving_average = prices_df['moving_average'].iloc[-1]
    low_price = prices_df['low'].iloc[-1]
    
    return moving_average, low_price

def calculate_dynamic_spread(moving_average, low_price, alpha=0.1):
    """Calculate the dynamic spread based on the difference between the moving average and the low price."""
    spread = alpha * (moving_average - low_price)
    print(spread)
    return max(0.02, spread)  # Ensure the spread is never less than 1 cent


def get_current_position(session, ticker):
    """Fetch the current position (inventory) for the given stock symbol."""
    response = session.get(f'{API_URL}/securities', headers=API_KEY)
    if response.status_code == 200:
        securities = response.json()
        for stock in securities:
            if stock['ticker'] == ticker:
                return stock.get('position', 0)  # Return position or 0 if not found
    else:
        raise Exception(f"Error fetching position: {response.status_code}")

def get_last_price(session, ticker):
    """Fetch the last traded price for the given stock symbol."""
    payload = {'ticker': ticker, 'limit': 1}
    response = session.get(f'{API_URL}/securities/history', params=payload, headers=API_KEY)
    if response.status_code == 200:
        price_history = response.json()
        if price_history:
            return price_history[0]['close']  # Return the last close price
    else:
        raise Exception(f"Error fetching last price: {response.status_code}")

def cancel_all_orders(session):
    """Cancel all open orders."""
    session.post(f'{API_URL}/commands/cancel?all=1', headers=API_KEY)

def submit_order(session, ticker, price, quantity, side):
    """Submit a buy or sell order to the RIT API."""
    payload = {
        'ticker': ticker,
        'type': 'LIMIT',
        'quantity': quantity,
        'action': side,  # "BUY" or "SELL"
        'price': price
    }
    response = session.post(f'{API_URL}/orders', params=payload, headers=API_KEY)
    return response.json()

def calculate_dynamic_order_size(current_position, max_position):
    """Calculate a dynamic order size based on current position."""
    order_size = int(MAX_ORDER_SIZE * abs(current_position) / max_position)
    return 5000 if order_size !=500  else 0# Keep within limits (500 to 5,000 shares)

def manage_orders(session, ticker, current_position, last_price, tick, spread=None):
    """Manage open orders based on market conditions."""
    open_orders = get_open_orders(session)
    
    # Check if time is close to end of session and cancel all orders if so
    if tick >= TIME_LIMIT:
        print("Time limit approaching. Canceling all orders.")
        cancel_all_orders(session)
        return

    # Check if there are not exactly two open orders (one buy and one sell)
    if len(open_orders) != 2 and len(open_orders) > 0:
        print("Imbalance in open orders. Canceling all and resetting orders.")
        cancel_all_orders(session)
        time.sleep(1)  # Give time for orders to be canceled

    # If position is long, place sell order to realize profits
    if current_position > 0:
        sell_price = last_price + spread
        sell_size = calculate_dynamic_order_size(current_position, MAX_POSITION)
        submit_order(session, ticker, sell_price, sell_size, 'SELL')
        print(f"Placed sell order for {sell_size} shares at {sell_price}")

    # If position is short or neutral, place buy order to accumulate inventory
    if current_position <= 0 or current_position < 25000:
        buy_price = last_price - spread
        buy_size = calculate_dynamic_order_size(current_position, MAX_POSITION)
        submit_order(session, ticker, buy_price, buy_size, 'BUY')
        print(f"Placed buy order for {buy_size} shares at {buy_price}")

def get_current_tick(session):
    """Fetch the current tick from the case."""
    response = session.get(f'{API_URL}/case', headers=API_KEY)
    if response.status_code == 200:
        case_data = response.json()
        return case_data['tick']
    else:
        raise Exception(f"Error fetching tick data: {response.status_code}")

def main():
    ticker = 'ALGO'  # The ticker symbol for the stock 
    alpha=0.1
    window=20
    with requests.Session() as session:
        session.headers.update(API_KEY)  # Set the API Key in headers
        
        # Main trading loop
        while True:
            # try:
                # Fetch price history and calculate moving average and low price
                prices_df = fetch_price_history(session, ticker)
                moving_average, low_price = calculate_moving_average_and_low(prices_df,window)

                # Calculate the dynamic spread
                spread = calculate_dynamic_spread(moving_average, low_price, alpha)

                # Fetch the current position and last traded price
                current_position = get_current_position(session, ticker)
                last_price = get_last_price(session, ticker)
                tick = get_current_tick(session)

                # Manage open orders based on the current market conditions and tick
                manage_orders(session, ticker, current_position, last_price, tick, spread)

                # Pause for a moment before the next iteration
                time.sleep(10)

            # except Exception as e:
            #     print(f"Error: {e}")
            #     break  # Exit the loop if there's an error

# Run the trading algorithm
if __name__ == '__main__':
    main()
