#!/usr/bin/env python3
import argparse
import json
import requests
import sys
import time
import random
import string
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        logger.debug(f"Sending POST request to {update_url} with word: {word}")
        
        # Send POST request with the word
        response = requests.post(
            update_url,
            json={'word': word}
        )
        
        # Check response status
        if response.status_code == 200:
            logger.info(f"Success! Server's greeting updated to '{word}'")
            return True
        else:
            logger.error(f"Server returned status code {response.status_code}")
            try:
                error_data = response.json()
                logger.error(f"Error message: {error_data.get('message', 'No message provided')}")
            except ValueError:
                logger.error(f"Non-JSON response: {response.text}")
            return False
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to server: {e}")
        return False

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Update the greeting word on the server')
    parser.add_argument('--server', required=True, help='Server URL (e.g., localhost:3000)')
    parser.add_argument('--word', help='The new greeting word to use (if not provided, a random word will be generated)')
    parser.add_argument('--interval', type=int, default=120, help='Time interval between updates in seconds (default: 120)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging', default=True)
    
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    logger.info(f"Client started - targeting server at {args.server}")
    logger.info(f"Update interval set to {args.interval} seconds")
    
    # Run in a loop, updating the greeting every specified interval
    try:
        while True:
            # Either use provided word or generate a random one
            if args.word and args.word.strip():
                word = args.word.strip()
                logger.info(f"Using provided word: {word}")
                # Generate a new random word for next time
                args.word = None
            else:
                word = generate_random_word()
                logger.info(f"Generated random word: {word}")
                
            # Update the greeting on the server
            update_result = update_greeting(args.server, word)
            
            if update_result:
                logger.info(f"Update successful, next update in {args.interval} seconds")
            else:
                logger.warning(f"Update failed, will retry in {args.interval} seconds")
            
            # Sleep for the specified interval
            logger.debug(f"Sleeping for {args.interval} seconds")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 