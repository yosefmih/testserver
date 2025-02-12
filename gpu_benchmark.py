#!/usr/bin/env python3
"""GPU Benchmark Script
This script performs various GPU tests including matrix operations, neural network inference,
and a stress test to validate GPU performance and memory usage.
"""

import time
import torch
from tqdm import tqdm

def get_gpu_memory_usage() -> float:
    """Return GPU memory usage in MB."""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024**2
    return 0

def test_matrix_operations(size: int = 5000) -> torch.Tensor:
    """Test large matrix operations on GPU."""
    print(f"\nTesting {size}x{size} matrix operations...")
    
    # Generate random matrices
    matrix_a = torch.randn(size, size, device='cuda')
    matrix_b = torch.randn(size, size, device='cuda')
    
    start_time = time.time()
    
    # Matrix multiplication
    result = torch.matmul(matrix_a, matrix_b)
    torch.cuda.synchronize()  # Ensure operation is complete
    
    end_time = time.time()
    print(f"Matrix multiplication time: {end_time - start_time:.2f} seconds")
    print(f"Current GPU memory usage: {get_gpu_memory_usage():.2f} MB")
    
    return result

def test_neural_network() -> None:
    """Test neural network operations using ResNet-50."""
    print("\nTesting neural network operations...")
    
    # Load pre-trained ResNet model
    model = torch.hub.load('pytorch/vision:v0.10.0', 'resnet50', pretrained=True)
    model = model.cuda()
    model.eval()
    
    # Generate random input
    input_tensor = torch.randn(16, 3, 224, 224, device='cuda')
    
    start_time = time.time()
    
    # Perform inference
    with torch.no_grad():
        output = model(input_tensor)
    torch.cuda.synchronize()
    
    end_time = time.time()
    print(f"Neural network inference time: {end_time - start_time:.2f} seconds")
    print(f"Current GPU memory usage: {get_gpu_memory_usage():.2f} MB")

def stress_test(duration: int = 10) -> None:
    """Perform a stress test by continuously allocating and deallocating memory."""
    print(f"\nPerforming stress test for {duration} seconds...")
    
    start_time = time.time()
    pbar = tqdm(total=duration, desc="Stress testing")
    
    while time.time() - start_time < duration:
        # Allocate large tensors
        tensors = [torch.randn(1000, 1000, device='cuda') for _ in range(10)]
        # Perform operations
        results = [torch.matmul(t, t) for t in tensors]
        # Clear memory
        del tensors
        del results
        torch.cuda.empty_cache()
        
        pbar.update(1)
        time.sleep(1)
    
    pbar.close()
    print(f"Final GPU memory usage: {get_gpu_memory_usage():.2f} MB")

def main() -> None:
    """Main function to run all GPU tests."""
    if not torch.cuda.is_available():
        print("No GPU available. Please check your CUDA installation.")
        return
    
    print(f"Using GPU: {torch.cuda.get_device_name()}")
    print(f"Initial GPU memory usage: {get_gpu_memory_usage():.2f} MB")
    
    try:
        # Test matrix operations
        test_matrix_operations()
        
        # Test neural network operations
        test_neural_network()
        
        # Perform stress test
        stress_test()
        
        print("\nAll GPU tests completed successfully!")
        
    except Exception as e:
        print(f"An error occurred during testing: {str(e)}")
    finally:
        # Clean up
        torch.cuda.empty_cache()
        print(f"Final GPU memory usage after cleanup: {get_gpu_memory_usage():.2f} MB")

if __name__ == "__main__":
    main() 