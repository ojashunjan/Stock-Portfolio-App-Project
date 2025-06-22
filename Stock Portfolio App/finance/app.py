import os
import requests
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():

    user_id = session["user_id"]

    user_portfolio = db.execute("SELECT * FROM portfolio WHERE user_id = ?", user_id)

    user_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)

    port_stock_value_total = db.execute("SELECT SUM(value) FROM portfolio WHERE user_id = ?", user_id)

    user_cash = user_cash[0]["cash"] if user_cash else 0

    port_stock_value_total = port_stock_value_total[0]["SUM(value)"] if port_stock_value_total else 0

    port_value = user_cash + (port_stock_value_total or 0)

    for stock in user_portfolio:
        for key, value in stock.items():
            if isinstance(value, float):
                stock[key] = usd(value)


    return render_template("/index.html",user_portfolio=user_portfolio, user_cash=usd(user_cash), port_value = usd(port_value))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        ticker = request.form.get("symbol").upper()
        try:
            ticker_data=lookup(ticker)
            if not ticker_data:
                raise ValueError
        except (requests.RequestException, ValueError, KeyError):
            return apology("invalid ticker symbol", 400)

        try:
            num_shares_to_buy = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid share count", 400)

        if num_shares_to_buy < 1:
            return apology("share count cannot be negative", 400)

        cost = ticker_data["price"] * num_shares_to_buy

        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        diff = user_cash[0]["cash"] - cost
        if  diff < 0:
            return apology(f"Cash Available: {user_cash[0]["cash"]} not enough to purchase stock buy of {cost}")



        db.execute("UPDATE users SET cash = ? WHERE id = ?", diff, session["user_id"])

        db.execute("INSERT INTO transactions (symbol, shares, cost, type, user_id) VALUES(?,?,?,?,?)", ticker, num_shares_to_buy, cost, "buy", session["user_id"])

        portfolio_ticker = db.execute("SELECT shares FROM portfolio WHERE user_id = ? AND stock_symbol = ?", session["user_id"], ticker)

        if portfolio_ticker:
            new_shares = portfolio_ticker[0]["shares"] + num_shares_to_buy
            db.execute("UPDATE portfolio SET stock_symbol = ?, shares = ?, share_price = ?, value = ? WHERE user_id = ?",ticker, new_shares, ticker_data["price"], new_shares*ticker_data["price"], session["user_id"])

        else:
            db.execute("INSERT INTO portfolio (user_id, stock_symbol, shares, share_price, value) VALUES (?,?,?,?,?)", session["user_id"], ticker, num_shares_to_buy, ticker_data["price"], cost)


        cost = usd(cost)
        flash(f"Purchase Successful!")
        return redirect("/")



    else:

        return render_template("/buy.html")


@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]

    user_transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)

    for transaction in user_transactions:
        for key, value in transaction.items():
            if key == "cost":
                transaction[key] = usd(value)



    return render_template("/history.html",user_transactions=user_transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        ticker = request.form.get("symbol")
        try:
            ticker_data=lookup(ticker)
            if not ticker_data:
                raise ValueError
        except (requests.RequestException, ValueError, KeyError):
            return apology("invalid ticker symbol", 400)
        symbol = ticker_data["symbol"]
        price = ticker_data["price"]

        return render_template("quoted.html", symbol=symbol, price=usd(price))
    else:

        return render_template("/quote.html")




@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        #makes sure username is not blank
        if not request.form.get("username") :
            return apology("must provide username", 400)
        #password not blank
        elif not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide password and confirmation", 400)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and confirmed password dont match", 400)

        new_username = request.form.get("username")
        new_hash = generate_password_hash(request.form.get("password"))

        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?,?)", new_username, new_hash)
        except ValueError:
            return apology("username already exists", 400)

        return redirect("/")

    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        ticker = request.form.get("symbol").upper()
        try:
            ticker_data=lookup(ticker)
            if not ticker_data:
                raise ValueError
        except (requests.RequestException, ValueError, KeyError):
            return apology("invalid ticker symbol", 400)
        current_stock_price = ticker_data["price"]
        try:
            num_shares_to_sell = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid share count", 400)

        if num_shares_to_sell < 1:
            return apology("share count cannot be negative", 400)

        try:
            results = db.execute("SELECT shares FROM portfolio WHERE user_id = ? and stock_symbol = ?", session["user_id"], ticker)
            if not results:
                return apology(f"no shares found for {ticker}", 400)
            current_share_count = results[0]["shares"]
            new_share_count = current_share_count - num_shares_to_sell
            if new_share_count < 0:
                raise ValueError
            elif new_share_count == 0:
                db.execute("DELETE FROM portfolio WHERE user_id = ? AND stock_symbol = ?", session["user_id"], ticker)
            else:
                db.execute("UPDATE portfolio SET shares = ?, value = ? WHERE user_id = ? AND stock_symbol = ?", new_share_count, current_stock_price * new_share_count, session["user_id"], ticker)

        except ValueError:
            return apology(f"not enough shares of {ticker}", 400)

        total_payout = current_stock_price * num_shares_to_sell

        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_payout, session["user_id"])

        db.execute("INSERT INTO transactions (symbol, shares, cost, type, user_id) VALUES(?,?,?,?,?)", ticker, num_shares_to_sell, total_payout, "sell", session["user_id"])


        return redirect("/")


    else:
        tickers = db.execute("SELECT stock_symbol FROM portfolio WHERE user_id = ?", session["user_id"])

        return render_template("sell.html", tickers=tickers)

@app.route("/add_cash", methods=["GET", "POST"])
def add_cash():

    if request.method == "POST":
        current_user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        try:
            cash_to_add = int(request.form.get("cash"))
        except ValueError:
            return apology("Cash must be an integer", 403)

        if not cash_to_add:
            return apology("No input for cash", 403)

        new_cash = current_user_cash[0]["cash"] + cash_to_add

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])

        return redirect("/")


    else:
        return render_template("add_cash.html")

