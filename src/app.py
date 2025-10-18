from dotenv import load_dotenv
from config import AppConfig
import logging_config

# Load .env file (do this BEFORE importing config)
load_dotenv()

# Now import config - it will use environment variables
# Create configuration from environment
config = AppConfig.from_env()

# Setup logging based on loaded configuration
logger = logging_config.setup_logging(config.appLog.log_dir,
                                      config.appLog.log_level,
                                      config.appLog.log_to_console,
                                      config.appLog.log_to_file,
                                      config.appLog.max_log_file_size_mb,
                                      config.appLog.log_backup_count,
                                      config.appLog.log_format)

if __name__ == '__main__':
    logger.info(config.can)
    logger.info(config.log)
    logger.info(config.appLog)
    logger.info(config.flask)