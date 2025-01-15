#!/usr/bin/env python3
import argparse
import psycopg2
import os
from datetime import datetime
from decimal import Decimal, getcontext

def init_db(conn):
    """Initialize the database table if it doesn't exist"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pi_digits (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                digits INTEGER,
                result NUMERIC(1000, 999)
            )
        """)
        conn.commit()

def get_cached_pi(conn, digits):
    """Get cached pi value if it exists"""
    with conn.cursor() as cur:
        cur.execute("SELECT result FROM pi_digits WHERE digits = %s ORDER BY timestamp DESC LIMIT 1", (digits,))
        result = cur.fetchone()
        return result[0] if result else None

def cache_pi(conn, digits, result):
    """Store computed pi value in the database"""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO pi_digits (digits, result) VALUES (%s, %s::numeric)", (digits, result))
        conn.commit()

def compute_pi(precision):
    """
    Compute Pi to the specified number of decimal places using the Chudnovsky algorithm
    """
    getcontext().prec = precision + 1
    C = 426880 * Decimal(10005).sqrt()
    L = 13591409
    X = 1
    M = 1
    K = 6
    S = L
    for i in range(1, precision):
        M = M * (K ** 3 - 16 * K) // (i ** 3)
        L += 545140134
        X *= -262537412640768000
        S += Decimal(M * L) / X
        K += 12
    pi = C / S
    return str(pi)

def main():
    parser = argparse.ArgumentParser(description='Compute Pi to a specified number of digits')
    parser.add_argument('--digits', type=int, default=10, 
                      help='Number of digits of Pi to compute (max 30)')
    
    args = parser.parse_args()
    
    if args.digits > 30:
        print("Maximum supported digits is 30")
        return
    
    if args.digits < 1:
        print("Number of digits must be positive")
        return
    
    # Get database credentials from environment variables
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')
    db_pass = os.environ.get('DB_PASS')

    # Validate required environment variables
    missing_vars = []
    for var_name in ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASS']:
        if not os.environ.get(var_name):
            missing_vars.append(var_name)
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_pass
        )
        
        # Initialize database table
        init_db(conn)
        
        # Check cache first
        cached_result = get_cached_pi(conn, args.digits)
        if cached_result:
            print(f"Found cached value of Pi to {args.digits} digits: {cached_result}")
            return
        
        # Compute new value
        pi = compute_pi(args.digits)
        
        # Cache the result
        cache_pi(conn, args.digits, pi)
        
        print(f"Computed and cached Pi to {args.digits} digits: {pi}")
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main() 