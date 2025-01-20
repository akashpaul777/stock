import signal
import requests
from time import sleep

# this class definition allows us to print error messages and stop the program when needed
class ApiException(Exception):
    pass

# this signal handler allows for a graceful shutdown when CTRL+C is pressed
def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

# Constants
API_KEY = {'X-API-Key': 'II679A88'}
shutdown = False
MAX_POSITION_LIMIT = 25000  # Maximum position limit
MAX_ORDER_SIZE = 6000  # Maximum size of each order
realized_profit_loss = 0  # Track realized P&L
position_m = 0  # Track position on main exchange
position_a = 0  # Track position on alternate exchange
print("Stocks")

# this helper method returns the current 'tick' of the running case
def get_tick(session):
    resp = session.get('http://localhost:9999/v1/case')
    if resp.ok:
        case = resp.json()
        return case['tick']
    raise ApiException('The API key provided in this Python code must match that in the RIT client (please refer to the API hyperlink in the client toolbar and/or the RIT – User Guide – REST API Documentation.pdf)')

# this helper method returns the bid and ask for a given security
def ticker_bid_ask(session, ticker):
    payload = {'ticker': ticker}
    resp = session.get('http://localhost:9999/v1/securities/book', params=payload)
    if resp.ok:
        book = resp.json()
        best_bid = book['bids'][0]['price'] if book['bids'] else None
        best_ask = book['asks'][0]['price'] if book['asks'] else None
        return best_bid, best_ask
    raise ApiException(f'Error fetching bid/ask for ticker {ticker}')

# Helper method to submit an order
def submit_order(session, ticker, action, quantity, order_type='MARKET'):
    order_data = {
        'ticker': ticker,
        'type': order_type,  # Use 'MARKET' or 'LIMIT'
        'action': action.upper(),  # "BUY" or "SELL"
        'quantity': quantity
    }
    resp = session.post('http://localhost:9999/v1/orders', params=order_data)
    if resp.ok:
        print(f"Successfully submitted {action} order for {quantity} shares of {ticker}.")
    else:
        print(f"Error submitting order: {resp.text}")

def main():
    global realized_profit_loss, position_m, position_a
    with requests.Session() as s:
        s.headers.update(API_KEY)
        tick = get_tick(s)
        
        # Trading loop
        while tick > 5 and tick < 295 and not shutdown:
            # Fetch bid/ask for both tickers
            crzy_m_bid, crzy_m_ask = ticker_bid_ask(s, 'CRZY_M')
            crzy_a_bid, crzy_a_ask = ticker_bid_ask(s, 'CRZY_A')

            # Check if an arbitrage opportunity exists in either direction
            if crzy_m_ask is not None and crzy_a_bid is not None and crzy_m_ask < crzy_a_bid:
                # Buy on CRZY_M and sell on CRZY_A
                order_size = min(MAX_ORDER_SIZE, MAX_POSITION_LIMIT - abs(position_m + position_a))
                if order_size > 0:
                    submit_order(s, 'CRZY_M', 'buy', order_size)
                    submit_order(s, 'CRZY_A', 'sell', order_size)
                     
                    position_m += order_size
                    position_a -= order_size
                    realized_profit_loss += (crzy_a_bid - crzy_m_ask) * order_size
                    print(f"Executed arbitrage trade: Buy CRZY_M @ {crzy_m_ask}, Sell CRZY_A @ {crzy_a_bid}")

            if crzy_a_ask is not None and crzy_m_bid is not None and crzy_a_ask < crzy_m_bid:
                # Buy on CRZY_A and sell on CRZY_M
                order_size = min(MAX_ORDER_SIZE, MAX_POSITION_LIMIT - abs(position_m + position_a))
                if order_size > 0:
                    submit_order(s, 'CRZY_A', 'buy', order_size)
                    submit_order(s, 'CRZY_M', 'sell', order_size)
                    position_a += order_size
                    position_m -= order_size
                    realized_profit_loss += (crzy_m_bid - crzy_a_ask) * order_size
                    print(f"Executed arbitrage trade: Buy CRZY_A @ {crzy_a_ask}, Sell CRZY_M @ {crzy_m_bid}")

            # Print current position and P&L
            print(f"Current position - Main: {position_m}, Alternate: {position_a}")
            print(f"Realized P&L: {realized_profit_loss}")

            # Check if we are exceeding the position limits
            # if abs(position_m) > MAX_POSITION_LIMIT or abs(position_a) > MAX_POSITION_LIMIT:
            #     print("Position limit exceeded. Stopping trading.")
            #     break

            # Sleep briefly to avoid overwhelming the API with too many requests
            sleep(1)

            # Update the tick to ensure the algorithm is still within trading time
            tick = get_tick(s)

if __name__ == '__main__':
    # Register the custom signal handler for graceful shutdowns
    signal.signal(signal.SIGINT, signal_handler)
    main()
