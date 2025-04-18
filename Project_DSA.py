from decimal import Decimal
import bcrypt
import random
import pymysql
import os
import json
from collections import deque
from datetime import datetime
import time
class Customer:
    def __init__(self, user_id=None, username=None, email=None, password=None, 
                 address=None, mobile_number=None, aadhaar_number=None, account_number=None, 
                 ifsc_code=None, card_number=None, encrypted_card_pin=None, balance=None, 
                 credit_score=None, loan_amount=None):
        
        self.user_id = user_id
        self.username = username
        self.email = email
        self.password_hash = self.encrypt_password(password) if password else None
        self.address = address
        self.mobile_number = mobile_number
        self.aadhaar_number = aadhaar_number
        self.account_number = account_number if account_number else self.generate_account_number()
        self.ifsc_code = ifsc_code if ifsc_code else "BANK1234567"
        self.card_number = card_number if card_number else self.generate_card_number()
        self.encrypted_card_pin = encrypted_card_pin if encrypted_card_pin else self.generate_encrypted_pin()
        self.balance = Decimal(balance) if balance is not None else Decimal('0.00')
        self.credit_score = int(credit_score) if credit_score is not None else 600
        self.loan_amount = Decimal(loan_amount) if loan_amount is not None else Decimal('0.00')
        self.transactions = deque(maxlen=10)

    @staticmethod
    def encrypt_password(password):
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(stored_hash, entered_password):
        return bcrypt.checkpw(entered_password.encode(), stored_hash.encode())

    @staticmethod
    def generate_encrypted_pin():
        pin = str(random.randint(1000, 9999))
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pin.encode(), salt).decode()

    @staticmethod
    def generate_account_number():
        return str(random.randint(1000000000, 9999999999))

    @staticmethod
    def generate_card_number():
        return str(random.randint(4000000000000000, 4999999999999999))

    def deposit(self, amount, db_manager, cache_manager):
        try:
            amount = Decimal(amount)
            if amount <= 0:
                print("❌ Invalid deposit amount!")
                return

            self.balance += amount
            self.credit_score = db_manager.update_credit_score(self.account_number)
            db_manager.update_customer(self)
            db_manager.insert_transaction(self.user_id, self.account_number, "Deposit", amount)
            
            # Update cache with new balance and credit score
            cache_manager.update_cache(self)
            cache_manager.add_transaction(
                self.account_number,
                "Deposit",
                amount,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            print(f"✅ Deposited ₹{amount}. New Balance: ₹{self.balance}")
            print(f"Credit Score: {self.credit_score}")

        except Exception as e:
            print(f"❌ Deposit failed: {e}")
            db_manager.conn.rollback()

    def withdraw(self, amount, db_manager, cache_manager):
        try:
            # Check cache first for quick balance verification
            cached_data = cache_manager.get_from_cache(self.account_number)
            if cached_data and float(amount) > float(cached_data['balance']):
                print("❌ Insufficient balance!")
                return

            amount = Decimal(amount)
            if amount <= 0 or amount > self.balance:
                print("❌ Invalid withdrawal amount!")
                return

            self.balance -= amount
            self.credit_score = db_manager.update_credit_score(self.account_number)
            db_manager.update_customer(self)
            db_manager.insert_transaction(self.user_id, self.account_number, "Withdrawal", -amount)
            
            # Update cache
            cache_manager.update_cache(self)
            cache_manager.add_transaction(
                self.account_number,
                "Withdrawal",
                -amount,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            print(f"✅ Withdrawn ₹{amount}. New Balance: ₹{self.balance}")
            print(f"Credit Score: {self.credit_score}")

        except Exception as e:
            print(f"❌ Withdrawal failed: {e}")
            db_manager.conn.rollback()

    def transfer_money(self, receiver, amount, db_manager, cache_manager):
        try:
            # Quick balance check using cache
            cached_data = cache_manager.get_from_cache(self.account_number)
            if cached_data and float(amount) > float(cached_data['balance']):
                print("❌ Insufficient balance!")
                return

            amount = Decimal(amount)
            if amount <= 0 or amount > self.balance:
                print("❌ Invalid transfer amount!")
                return

            db_manager.conn.begin()
            try:
                self.balance -= amount
                receiver.balance += amount

                self.credit_score = db_manager.update_credit_score(self.account_number)
                receiver.credit_score = db_manager.update_credit_score(receiver.account_number)

                for customer in [self, receiver]:
                    db_manager.update_customer(customer)
                    cache_manager.update_cache(customer)

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Record transactions in both DB and cache
                for cust, amt, desc in [(self, -amount, f"Transfer to {receiver.account_number}"),
                                      (receiver, amount, f"Transfer from {self.account_number}")]:
                    db_manager.insert_transaction(cust.user_id, cust.account_number, desc, amt)
                    cache_manager.add_transaction(cust.account_number, desc, amt, timestamp)

                db_manager.conn.commit()
                print(f"✅ Transferred ₹{amount} to {receiver.account_number}")
                print(f"Your Credit Score: {self.credit_score}")

            except Exception as e:
                db_manager.conn.rollback()
                raise e

        except Exception as e:
            print(f"❌ Transfer failed: {e}")
    def take_loan(self, amount, db_manager, cache_manager):
        try:
            amount = Decimal(amount)
            
            # Check minimum loan amount
            if amount < 500:
                print("❌ Minimum loan amount is ₹500!")
                return

            # Check loan eligibility
            eligible, result = db_manager.check_loan_eligibility(self.account_number, amount)
            if not eligible:
                print(f"❌ Loan request denied: {result}")
                return

            # Process loan
            self.loan_amount += amount
            self.balance += amount
            self.credit_score = result["credit_score"]  # Update credit score

            # Update database
            query = """UPDATE customers 
                      SET balance = %s, loan_amount = %s, credit_score = %s 
                      WHERE account_number = %s"""
            db_manager.cursor.execute(query, (
                self.balance, 
                self.loan_amount,
                self.credit_score,
                self.account_number
            ))
            db_manager.conn.commit()

            # Record transaction and update cache
            db_manager.insert_transaction(self.user_id, self.account_number, "Loan Taken", amount)
            cache_manager.update_cache(self)
            
            print(f"✅ Loan of ₹{amount} granted")
            print(f"Interest Rate: {result['interest_rate']}%")
            print(f"Credit Score: {self.credit_score}")
            print(f"New Balance: ₹{self.balance}")
            print(f"Total Loan Amount: ₹{self.loan_amount}")

        except Exception as e:
            print(f"❌ Loan failed: {e}")
            db_manager.conn.rollback()
    def return_loan(self, amount, db_manager, cache_manager):
        try:
            # Quick check using cache first
            cached_data = cache_manager.get_from_cache(self.account_number)
            if cached_data:
                if float(amount) > float(cached_data['balance']) or float(amount) > float(cached_data['loan_amount']):
                    print("❌ Invalid loan repayment amount!")
                    return

            amount = Decimal(amount)
            if amount <= 0 or amount > self.balance or amount > self.loan_amount:
                print("❌ Invalid loan repayment amount!")
                return

            self.loan_amount -= amount
            self.balance -= amount
            
            # Update credit score for loan repayment
            self.credit_score = db_manager.update_credit_score(self.account_number)
            
            # Update both database and cache
            db_manager.update_customer(self)
            cache_manager.update_cache(self)
            
            # Record transaction in both DB and cache
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db_manager.insert_transaction(self.user_id, self.account_number, "Loan Repayment", -amount)
            cache_manager.add_transaction(self.account_number, "Loan Repayment", -amount, timestamp)
            
            print(f"✅ Loan repayment of ₹{amount} successful")
            print(f"Remaining loan: ₹{self.loan_amount}")
            print(f"New Balance: ₹{self.balance}")
            print(f"Credit Score: {self.credit_score}")

        except Exception as e:
            print(f"❌ Loan repayment failed: {e}")
            db_manager.conn.rollback()

class DatabaseManager:
    def __init__(self, cache_manager=None):
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
        self.conn = pymysql.connect(
            host="localhost",
            user="root",
            password=self.MYSQL_PASSWORD,
            database="bank_system"
        )
        self.cursor = self.conn.cursor()
        self.cache_manager = cache_manager
        print("✅ Connected to MySQL - Database: bank_system")

    def insert_customer(self, customer):
        try:
            query = """INSERT INTO customers (
                username, email, password_hash, address, mobile_number, 
                aadhaar_number, account_number, ifsc_code, card_number, 
                encrypted_card_pin, balance, credit_score, loan_amount
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            data = (
                customer.username, customer.email, customer.password_hash,
                customer.address, customer.mobile_number, customer.aadhaar_number,
                customer.account_number, customer.ifsc_code, customer.card_number,
                customer.encrypted_card_pin, customer.balance, customer.credit_score,
                customer.loan_amount
            )
            
            self.cursor.execute(query, data)
            self.conn.commit()
            self.cache_manager.update_cache(customer)
            print("✅ Customer created successfully")
            
        except pymysql.IntegrityError as e:
            print(f"❌ Customer already exists: {e}")
            self.conn.rollback()
        except Exception as e:
            print(f"❌ Error creating customer: {e}")
            self.conn.rollback()

    def fetch_customer(self, account_number):
        try:
            query = """SELECT user_id, username, email, password_hash, address,
                      mobile_number, aadhaar_number, balance, loan_amount,
                      encrypted_card_pin, account_number, ifsc_code, card_number,
                      credit_score FROM customers WHERE account_number = %s"""
            self.cursor.execute(query, (account_number,))
            result = self.cursor.fetchone()
            
            if result:
                return Customer(
                    user_id=result[0],
                    username=result[1],
                    email=result[2],
                    password=None,
                    address=result[4],
                    mobile_number=result[5],
                    aadhaar_number=result[6],
                    balance=result[7],
                    loan_amount=result[8],
                    encrypted_card_pin=result[9],
                    account_number=result[10],
                    ifsc_code=result[11],
                    card_number=result[12],
                    credit_score=result[13]
                )
            return None
        except Exception as e:
            print(f"❌ Error fetching customer: {e}")
            return None

    def update_customer(self, customer):
        try:
            query = """UPDATE customers 
                      SET balance = %s, credit_score = %s, loan_amount = %s 
                      WHERE account_number = %s"""
            self.cursor.execute(query, (
                customer.balance,
                customer.credit_score,
                customer.loan_amount,
                customer.account_number
            ))
            self.conn.commit()
            self.cache_manager.update_cache(customer)
            print(f"✅ Customer {customer.account_number} updated")
        except Exception as e:
            print(f"❌ Update failed: {e}")
            self.conn.rollback()

    def delete_customer(self, account_number):
        try:
            self.cursor.execute("DELETE FROM transaction_record WHERE account_number = %s", 
                              (account_number,))
            self.cursor.execute("DELETE FROM customers WHERE account_number = %s", 
                              (account_number,))
            self.conn.commit()
            self.cache_manager.remove_from_cache(account_number)
            print(f"✅ Customer {account_number} deleted")
        except Exception as e:
            print(f"❌ Deletion failed: {e}")
            self.conn.rollback()

    def insert_transaction(self, user_id, account_number, transaction_type, amount):
        try:
            query = """INSERT INTO transaction_record 
                      (user_id, account_number, transaction_type, amount) 
                      VALUES (%s, %s, %s, %s)"""
            self.cursor.execute(query, (user_id, account_number, transaction_type, amount))
            self.conn.commit()
            
            # Update transaction cache
            if self.cache_manager:
                self.cache_manager.add_transaction(
                    account_number,
                    transaction_type,
                    amount,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            print(f"✅ Transaction recorded: {transaction_type} ₹{amount}")
        except Exception as e:
            print(f"❌ Transaction recording failed: {e}")
            self.conn.rollback()

    def fetch_transactions(self, account_number):
        try:
            query = """SELECT transaction_type, amount, timestamp 
                      FROM transaction_record 
                      WHERE account_number = %s 
                      ORDER BY timestamp DESC LIMIT 10"""
            self.cursor.execute(query, (account_number,))
            transactions = self.cursor.fetchall()
            
            if transactions:
                print("\n===== Transaction History =====")
                for t in transactions:
                    print(f"{t[2]} - {t[0]} ₹{t[1]}")
            else:
                print("No transactions found.")
        except Exception as e:
            print(f"❌ Error fetching transactions: {e}")

    def authenticate_customer(self, email, password):
        try:
            query = """SELECT user_id, username, email, password_hash, address,
                      mobile_number, aadhaar_number, balance, loan_amount,
                      encrypted_card_pin, account_number, ifsc_code, card_number,
                      credit_score FROM customers WHERE email = %s"""
            self.cursor.execute(query, (email,))
            result = self.cursor.fetchone()
            
            if result and bcrypt.checkpw(password.encode(), result[3].encode()):
                return Customer(
                    user_id=result[0],
                    username=result[1],
                    email=result[2],
                    password=None,
                    address=result[4],
                    mobile_number=result[5],
                    aadhaar_number=result[6],
                    balance=result[7],
                    loan_amount=result[8],
                    encrypted_card_pin=result[9],
                    account_number=result[10],
                    ifsc_code=result[11],
                    card_number=result[12],
                    credit_score=result[13]
                )
            return None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    def update_credit_score(self, account_number):
        """Calculate and update customer's credit score."""
        try:
            # Get transaction history
            query = """SELECT transaction_type, amount, timestamp 
                      FROM transaction_record 
                      WHERE account_number = %s 
                      AND timestamp >= DATE_SUB(NOW(), INTERVAL 6 MONTH)"""
            self.cursor.execute(query, (account_number,))
            transactions = self.cursor.fetchall()
            
            # Get current balance and loan info
            query = "SELECT balance, loan_amount FROM customers WHERE account_number = %s"
            self.cursor.execute(query, (account_number,))
            balance, loan_amount = self.cursor.fetchone()
            
            # Base score calculation
            base_score = 600
            
            # Balance factor (up to +200)
            balance_factor = min(200, int(float(balance) / 1000))
            
            # Transaction patterns
            deposits = sum(1 for t in transactions if t[0] == "Deposit" and float(t[1]) >= 1000)
            deposit_score = min(100, deposits * 20)
            
            # Loan repayment history
            repayments = sum(1 for t in transactions if t[0] == "Loan Repayment")
            repayment_score = min(150, repayments * 30)
            
            # Penalties for negative behavior
            failed_transactions = sum(1 for t in transactions if t[0] in ["Failed", "Bounced"])
            penalty = min(200, failed_transactions * 50)
            
            # Calculate final score
            credit_score = min(900, base_score + balance_factor + deposit_score + 
                             repayment_score - penalty)
            
            # Update credit score
            query = "UPDATE customers SET credit_score = %s WHERE account_number = %s"
            self.cursor.execute(query, (credit_score, account_number))
            self.conn.commit()
            
            return credit_score
            
        except Exception as e:
            print(f"❌ Error updating credit score: {e}")
            self.conn.rollback()
            return None

    def check_loan_eligibility(self, account_number, requested_amount):
        """Check if customer is eligible for loan."""
        try:
            # Get customer details
            query = """SELECT balance, credit_score, loan_amount 
                      FROM customers 
                      WHERE account_number = %s"""
            self.cursor.execute(query, (account_number,))
            balance, credit_score, current_loan = self.cursor.fetchone()
            
            # Update credit score first
            credit_score = self.update_credit_score(account_number)
            if not credit_score:
                return False, "Failed to calculate credit score"
            
            # Calculate loan multiplier based on credit score
            if credit_score >= 800:
                multiplier = 3.0  # Can borrow up to 3x balance
            elif credit_score >= 700:
                multiplier = 2.0  # Can borrow up to 2x balance
            elif credit_score >= 600:
                multiplier = 1.0  # Can borrow up to 1x balance
            else:
                return False, f"Credit score too low ({credit_score}/900)"
            
            max_loan = float(balance) * multiplier
            
            if float(requested_amount) > max_loan:
                return False, f"Maximum loan amount allowed: ₹{max_loan:.2f}"
                
            return True, {
                "credit_score": credit_score,
                "interest_rate": max(8, 15 - (credit_score - 600) / 100),
                "max_loan": max_loan
            }
            
        except Exception as e:
            print(f"❌ Error checking loan eligibility: {e}")
            return False, "System error in loan eligibility check"

    def close(self):
        try:
            self.conn.close()
            print("✅ Database connection closed")
        except Exception as e:
            print(f"❌ Error closing connection: {e}")

class CacheManager:
    def __init__(self, cache_file="cache.json", max_transactions=10):
        self.cache_file = cache_file
        self.customer_cache = {}  # Dictionary for fast customer lookup
        self.transaction_history = {}  # Dictionary of deques for each customer
        self.max_transactions = max_transactions
        self.load_cache()

    def load_cache(self):
        try:
            with open(self.cache_file, "r") as file:
                data = json.load(file)
                self.customer_cache = data.get("customers", {})
                # Initialize transaction deques
                for acc_num in self.customer_cache:
                    self.transaction_history[acc_num] = deque(maxlen=self.max_transactions)
        except (FileNotFoundError, json.JSONDecodeError):
            self.customer_cache = {}

    def update_cache(self, customer):
        # Update customer data in cache
        self.customer_cache[customer.account_number] = {
            "username": customer.username,
            "balance": float(customer.balance),
            "credit_score": customer.credit_score,
            "loan_amount": float(customer.loan_amount),
            "email": customer.email,
            "address": customer.address,
            "last_updated": time.time()
        }
        self.save_cache()

    def add_transaction(self, account_number, transaction_type, amount, timestamp):
        # Initialize deque if not exists
        if account_number not in self.transaction_history:
            self.transaction_history[account_number] = deque(maxlen=self.max_transactions)
        
        # Add transaction to history
        self.transaction_history[account_number].appendleft({
            "type": transaction_type,
            "amount": float(amount),
            "timestamp": timestamp
        })

    def get_cached_transactions(self, account_number):
        return list(self.transaction_history.get(account_number, deque()))

    def get_from_cache(self, account_number):
        if account_number in self.customer_cache:
            data = self.customer_cache[account_number]
            # Check if cache is not too old (30 minutes)
            if time.time() - data.get("last_updated", 0) < 1800:
                print("✅ Data retrieved from cache")
                return data
        return None

    def save_cache(self):
        cache_data = {
            "customers": self.customer_cache,
            "last_saved": time.time()
        }
        with open(self.cache_file, "w") as file:
            json.dump(cache_data, file, indent=4)

    def remove_from_cache(self, account_number):
        if account_number in self.customer_cache:
            del self.customer_cache[account_number]
            if account_number in self.transaction_history:
                del self.transaction_history[account_number]
            self.save_cache()

def main():
    cache_manager = CacheManager()
    db_manager = DatabaseManager(cache_manager)
    
    while True:
        print("\n===== Banking System =====")
        print("1. Create Account")
        print("2. Login")
        print("3. Exit")
        
        try:
            choice = input("Choose an option: ").strip()
            
            if choice == "1":
                try:
                    print("\n--- Create New Account ---")
                    username = input("Name: ").strip()
                    email = input("Email: ").strip()
                    password = input("Password: ").strip()
                    address = input("Address: ").strip()
                    mobile = input("Mobile (10 digits): ").strip()
                    aadhaar = input("Aadhaar (12 digits): ").strip()
                    
                    if len(mobile) != 10 or len(aadhaar) != 12:
                        print("❌ Invalid mobile or aadhaar length!")
                        continue
                    
                    customer = Customer(
                        username=username,
                        email=email,
                        password=password,
                        address=address,
                        mobile_number=mobile,
                        aadhaar_number=aadhaar
                    )
                    
                    db_manager.insert_customer(customer)
                    
                except Exception as e:
                    print(f"❌ Account creation failed: {e}")
                    
            elif choice == "2":
                print("\n--- Login ---")
                email = input("Email: ").strip()
                password = input("Password: ").strip()
                
                customer = db_manager.authenticate_customer(email, password)
                if customer:
                    print(f"✅ Welcome back, {customer.username}!")
                    print(f"Account Number: {customer.account_number}")
                    
                    while True:
                        print("\n=== Operations ===")
                        print("1. Check Balance")
                        print("2. Deposit")
                        print("3. Withdraw")
                        print("4. Transfer")
                        print("5. Take Loan")
                        print("6. Return Loan")
                        print("7. Transaction History")
                        print("8. Logout")
                        
                        op = input("Choose operation: ").strip()
                        
                        if op == "8":
                            print("✅ Logged out successfully")
                            break
                            
                        if op == "1":
                            print(f"Balance: ₹{customer.balance}")
                            print(f"Loan Amount: ₹{customer.loan_amount}")
                            
                        elif op == "2":
                            try:
                                amount = float(input("Amount: "))
                                customer.deposit(amount, db_manager, cache_manager)
                            except ValueError:
                                print("❌ Invalid amount format!")
                            
                        elif op == "3":
                            try:
                                amount = float(input("Amount: "))
                                customer.withdraw(amount, db_manager, cache_manager)
                            except ValueError:
                                print("❌ Invalid amount format!")
                            
                        elif op == "4":
                            receiver_acc = input("Receiver account: ")
                            if receiver_acc == customer.account_number:
                                print("❌ Cannot transfer to same account!")
                                continue
                                
                            receiver = db_manager.fetch_customer(receiver_acc)
                            if receiver:
                                try:
                                    amount = float(input("Amount: "))
                                    customer.transfer_money(receiver, amount, db_manager, cache_manager)
                                except ValueError:
                                    print("❌ Invalid amount format!")
                            else:
                                print("❌ Receiver not found!")
                                
                        elif op == "5":
                            try:
                                amount = float(input("Loan amount: "))
                                customer.take_loan(amount, db_manager, cache_manager)
                            except ValueError:
                                print("❌ Invalid amount format!")
                            
                        elif op == "6":
                            try:
                                amount = float(input("Repayment amount: "))
                                customer.return_loan(amount, db_manager, cache_manager)
                            except ValueError:
                                print("❌ Invalid amount format!")
                            
                        elif op == "7":
                            db_manager.fetch_transactions(customer.account_number)
                        else:
                            print("❌ Invalid operation!")
                else:
                    print("❌ Invalid credentials!")
                    
            elif choice == "3":
                print("✅ Thank you for using our banking system. Goodbye!")
                db_manager.close()
                break
            else:
                print("❌ Invalid choice!")
                
        except KeyboardInterrupt:
            print("\n\n⚠️ Program interrupted by user")
            db_manager.close()
            break
        except Exception as e:
            print(f"❌ System error: {e}")
            db_manager.close()
            break

if __name__ == "__main__":
    main()