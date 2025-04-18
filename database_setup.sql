CREATE DATABASE bank_system;

USE bank_system;

CREATE TABLE customers (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    address TEXT NOT NULL,
    mobile_number VARCHAR(15) UNIQUE NOT NULL,
    aadhaar_number VARCHAR(12) UNIQUE NOT NULL,
    account_number VARCHAR(20) UNIQUE NOT NULL,
    ifsc_code VARCHAR(11) NOT NULL,
    card_number VARCHAR(16) UNIQUE NOT NULL,
    encrypted_card_pin VARCHAR(255) NOT NULL,
    balance DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    credit_score INT DEFAULT 600,
    loan_amount DECIMAL(15,2) DEFAULT 0.00
);

CREATE TABLE transaction_record (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    account_number VARCHAR(20) NOT NULL,
    transaction_type ENUM('Deposit', 'Withdrawal', 'Loan Repayment') NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_number) REFERENCES customers(account_number) ON DELETE CASCADE
);
