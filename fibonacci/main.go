package main

import (
	"fmt"
	"os"
	"strconv"
)

// fibRecursive calculates the nth Fibonacci number using recursion
func fibRecursive(n int) int {
	if n <= 1 {
		return n
	}
	return fibRecursive(n-1) + fibRecursive(n-2)
}

// fibIterative calculates the nth Fibonacci number using iteration
func fibIterative(n int) int {
	if n <= 1 {
		return n
	}

	prev, curr := 0, 1
	for i := 2; i <= n; i++ {
		prev, curr = curr, prev+curr
	}
	return curr
}

func main() {
	if len(os.Args) != 2 {
		fmt.Println("Usage: go run main.go <n>")
		fmt.Println("where n is the position of the Fibonacci number to compute")
		os.Exit(1)
	}

	n, err := strconv.Atoi(os.Args[1])
	if err != nil {
		fmt.Printf("Error: Invalid number '%s'\n", os.Args[1])
		os.Exit(1)
	}

	if n < 0 {
		fmt.Println("Error: Please provide a non-negative number")
		os.Exit(1)
	}

	// Using iterative method as it's more efficient
	result := fibIterative(n)
	fmt.Printf("The %dth Fibonacci number is: %d\n", n, result)
}
