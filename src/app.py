from dotenv import load_dotenv
from config import AppConfig
import os

# Load .env file (do this BEFORE importing config)
load_dotenv()

# Now import config - it will use environment variables
# Create configuration from environment
config = AppConfig.from_env()

if __name__ == '__main__':
    print("Loaded CAN Configuration:")
    print(config.can)

    print("Loaded Logging Configuration:")
    print(config.log)

    print(f"App will run on {config.host}:{config.port} with debug={config.debug} and log_level={config.log_level}")