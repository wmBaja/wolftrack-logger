def format_can_data(data: bytes) -> str:
    """
    Format CAN data as hex string.
    
    Args:
        data: CAN data bytes
    
    Returns:
        Formatted string (e.g., "01 02 03 04")
    
    Example:
        >>> format_can_data(bytes([0x01, 0x02, 0x03]))
        '01 02 03'
    """
    return ''.join(f'{b:02X}' for b in data)