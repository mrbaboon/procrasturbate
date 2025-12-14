"""Example code for testing the AI reviewer with debounce."""

import os
import sys  # Another unused import


def get_user_data(user_id):
    """Fetch user data from database."""
    # SQL injection vulnerability for reviewer to catch
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return execute_query(query)


def process_password(password):
    """Process user password."""
    # Hardcoded secret - reviewer should catch this
    api_key = "sk-1234567890abcdef"

    # Missing input validation
    return hash_password(password)


def calculate_total(items):
    """Calculate total price."""
    total = 0
    for item in items:
        # Potential KeyError if 'price' missing
        total += item['price'] * item['quantity']
    return total


# Unused import at top (os) - reviewer should note this

def hash_password(password):
    """Placeholder for password hashing."""
    return password  # Just a placeholder


def execute_query(query):
    """Placeholder for query execution."""
    return []  # Just a placeholder
# Test context file loading
# More test content
