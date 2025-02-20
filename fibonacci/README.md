# Fibonacci Number Calculator

This Go module provides a simple command-line tool to calculate the nth Fibonacci number.

## Implementation Details

The module includes two implementations:
1. An iterative solution (used by default) - O(n) time complexity
2. A recursive solution (included but not used) - O(2^n) time complexity

The iterative solution is used by default as it's more efficient.

## Usage

To run the program:

```bash
go run main.go <n>
```

Where `<n>` is the position of the Fibonacci number you want to calculate.

### Examples

```bash
# Calculate the 10th Fibonacci number
go run main.go 10

# Calculate the 20th Fibonacci number
go run main.go 20
```

### Note
- The program accepts non-negative integers only
- The first few Fibonacci numbers are: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, ...
- F(0) = 0, F(1) = 1, F(n) = F(n-1) + F(n-2) for n > 1 