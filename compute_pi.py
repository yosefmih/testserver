#!/usr/bin/env python3
import argparse
from decimal import Decimal, getcontext

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
    
    # Compute pi
    pi = compute_pi(args.digits)
    print(f"Computed Pi to {args.digits} digits: {pi}")

if __name__ == "__main__":
    main() 