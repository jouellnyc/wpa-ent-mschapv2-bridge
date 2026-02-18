import logging
import subprocess
from datetime import datetime

# Constants for magic numbers
TIMEOUT = 30
RETRY_LIMIT = 3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NetworkMonitor:
    """
    Class to encapsulate network monitoring logic.
    """

    def __init__(self, monitor_ip):
        self.monitor_ip = monitor_ip

    def ping(self):
        """
        Pings the designated IP address and returns the result.
        """
        retry_count = 0
        while retry_count < RETRY_LIMIT:
            try:
                logging.info(f'Pinging {self.monitor_ip}...')
                result = subprocess.run(['ping', '-c', '4', self.monitor_ip],
                                        check=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                logging.info('Ping successful.')
                return result.stdout.decode()
            except subprocess.CalledProcessError as e:
                logging.error(f'Ping failed: {e.stderr.decode()}')
                retry_count += 1
            except Exception as e:
                logging.error(f'An unexpected error occurred: {str(e)}')
                break
        logging.warning('Max retries reached. Ping failed.')
        return None

    def get_timestamp(self):
        """
        Returns the current timestamp in a formatted string.
        """
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

# Example usage:
if __name__ == '__main__':
    monitor = NetworkMonitor('8.8.8.8')
    print(monitor.ping())
    print(monitor.get_timestamp())