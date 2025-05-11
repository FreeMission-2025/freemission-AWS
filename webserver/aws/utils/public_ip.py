import requests
from .logger import Log

def get_public_ip():
    try:
        # Try to get the public IP from ipify
        response = requests.get("https://api.ipify.org", timeout=5)
        # If the request is successful, return the public IP
        if response.status_code == 200:
            return response.text
        else:
            raise Exception("Failed to fetch from ipify")
    except (requests.exceptions.RequestException, Exception) as e:
        Log.warning(f"Error fetching IP from ipify: {e}")
        # Backup to another public IP service (e.g., httpbin)
        try:
            response = requests.get("https://httpbin.org/ip", timeout=5)
            if response.status_code == 200:
                return response.json()['origin']  # Extract public IP from JSON response
            else:
                raise Exception("Failed to fetch from httpbin")
        except requests.exceptions.RequestException as e:
            Log.warning(f"Error fetching IP from httpbin: {e}")
            return '127.0.0.1'
