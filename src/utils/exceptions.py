class CANConnectionException(Exception):
    """Custom exception for CAN connection errors."""
    pass

class DBCLoadException(Exception):
    """Custom exception for DBC loading errors."""
    pass

class FileNameValidationException(Exception):
    """Custom exception for validation errors."""
    pass

class SessionAlreadyActiveException(Exception):
    """Custom exception for existing session errors."""
    pass

class SessionNotActiveException(Exception):
    """Custom exception for non-active session errors."""
    pass