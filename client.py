#!/usr/bin/env python3
import argparse
import json
import requests
import sys
import time
import random
import string

def generate_random_word(length=8):
    """Generate a random string to use as a greeting word."""
    letters = string.ascii_uppercase
    return ''.join(random.choice(letters) for _ in range(length))

def update_greeting(server_url, word):
    """Send a request to update the server's greeting word."""
    # Normalize the URL
    if not server_url.startswith(('http://', 'https://')):
        server_url = f'http://{server_url}'
    
    # Ensure URL doesn't end with a slash
    server_url = server_url.rstrip('/')
    
    # Construct the full URL
    update_url = f"{server_url}/update-greeting"
    
    try:
        # Send POST request with the word
        response = requests.post(
            update_url,
            json={'word': word}
        )
        
        # Check response status
        if response.status_code == 200:
            print(f"Success! Server's greeting updated to '{word}'")
            return True
        else:
            print(f"Error: Server returned status code {response.status_code}")
            try:
                error_data = response.json()
                print(f"Message: {error_data.get('message', 'No message provided')}")
            except ValueError:
                print(f"Response: {response.text}")
            return False
    
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to server: {e}")
        return False

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Update the greeting word on the server')
    parser.add_argument('--server', required=True, help='Server URL (e.g., localhost:3000)')
    parser.add_argument('--word', help='The new greeting word to use (if not provided, a random word will be generated)')
    parser.add_argument('--interval', type=int, default=120, help='Time interval between updates in seconds (default: 120)')
    
    args = parser.parse_args()
    
    # Run in a loop, updating the greeting every specified interval
    try:
        while True:
            # Either use provided word or generate a random one
            if args.word and args.word.strip():
                word = args.word.strip()
                # Generate a new random word for next time
                args.word = None
            else:
                word = generate_random_word()
                
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sending word: {word}")
            
            # Update the greeting on the server
            update_greeting(args.server, word)
            
            # Sleep for the specified interval
            print(f"Sleeping for {args.interval} seconds before next update...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\nClient stopped by user.")
        sys.exit(0)

if __name__ == '__main__':
    main() 