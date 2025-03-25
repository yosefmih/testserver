#!/usr/bin/env python3
import argparse
import json
import requests
import sys

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
    parser.add_argument('word', help='The new greeting word to use')
    
    args = parser.parse_args()
    
    # Check if a word was provided
    if not args.word.strip():
        print("Error: Greeting word cannot be empty")
        sys.exit(1)
    
    # Update the greeting on the server
    success = update_greeting(args.server, args.word)
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 