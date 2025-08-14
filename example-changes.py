# Example changes to demonstrate hot reload

# Add this to server.py to see hot reload in action:

# 1. Add a new route for testing hot reload
"""
@app.route('/hot-reload-test')
def hot_reload_test():
    return {
        'message': 'Hot reload is working! 🔥',
        'timestamp': time.time(),
        'hostname': HOSTNAME,
        'hot_reload': True
    }
"""

# 2. Modify an existing route to show changes
"""
# Find the root route and add hot reload indicator:
@app.route('/')
def home():
    return {
        'message': 'Hello from txx app with HOT RELOAD! 🚀',
        'hostname': HOSTNAME,
        'hot_reload_active': True,
        'timestamp': time.time()
    }
"""

# 3. Add console logging to see restart
"""
# Add at the top of server.py after imports:
print(f"🔄 Server restarted at {datetime.now()}")
print(f"🎯 Hot reload active on {HOSTNAME}")
"""