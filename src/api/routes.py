"""
Flask REST API routes for CAN logging application.

This module defines all HTTP endpoints for:
- Health checks and system status
- Session management (start/stop logging)
- DBC file management (upload, query)
- Log file operations (list, download, delete)

The routes are registered dynamically via register_routes() function to allow
dependency injection of managers and configuration.
"""

from flask import request, jsonify, send_file, Flask
from pathlib import Path

from logging_config import get_logger
from utils.exceptions import (
    SessionAlreadyActiveException,
    SessionNotActiveException,
    FileNameValidationException
)


logger = get_logger(__name__)


def register_routes(
    app: Flask,
    session_manager,
    dbc_manager,
    log_config
) -> None:
    """
    Register all API routes with the Flask application.
    
    Args:
        app: Flask application instance
        session_manager: SessionManager instance for controlling logging sessions
        dbc_manager: DBCManager instance for handling DBC database files
        log_config: CANLogConfig instance for accessing configuration
    """
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """
        Health check endpoint for monitoring system status.
        
        Returns:
            JSON response with system health indicators:
            - status: 'healthy' or 'unhealthy'
            - session: whether a logging session is active
            - can_connected: whether CAN interface is connected
            - dbc_loaded: whether a DBC file is loaded
            
            Status codes:
            - 200: System is healthy
            - 500: System is unhealthy (with error details)
        """
        try:
            from src.can_interface import CANInterface

            status = {
                'status': 'healthy',
                'session': session_manager.is_active(),
                'can_connected': session_manager.can_interface.is_connected(),
                'dbc_loaded': dbc_manager.is_loaded()
            }

            return jsonify(status), 200

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 500

    @app.route('/api/session/start', methods=['POST'])
    def start_session():
        """
        Start a new CAN logging session.
        
        Request body (JSON, optional):
            {
                "filename_template": "log_%T_%C"  // Optional custom filename template
            }
        
        Returns:
            JSON response with operation result:
            - success: boolean indicating if session started
            - message: descriptive message about the operation
            - error: error message (only if failed)
            
            Status codes:
            - 200: Session started successfully
            - 400: Invalid request or session already active
            - 500: Internal server error
        """
        try:
            data = request.get_json() or {}
            filename_template = data.get('filename_template', None)

            success, message = session_manager.start(filename_template)

            return jsonify({
                'success': success,
                'message': message
            }), 200 if success else 400

        except SessionAlreadyActiveException as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400

        except FileNameValidationException as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400

        except Exception as e:
            logger.error(f"Error starting session: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Internal server error'
            }), 500

    @app.route('/api/session/stop', methods=['POST'])
    def stop_session():
        """
        Stop the current CAN logging session.
        
        Returns:
            JSON response with operation result:
            - success: boolean indicating if session stopped
            - message: summary of the session (messages logged, duration, etc.)
            - error: error message (only if failed)
            
            Status codes:
            - 200: Session stopped successfully
            - 400: No active session to stop
            - 500: Internal server error
        """
        try:
            success, message = session_manager.stop()

            return jsonify({
                'success': success,
                'message': message
            }), 200 if success else 400

        except SessionNotActiveException as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400

        except Exception as e:
            logger.error(f"Error stopping session: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Internal server error'
            }), 500

    @app.route('/api/session/status', methods=['GET'])
    def get_session_status():
        """
        Get detailed status of the current or last logging session.
        
        Returns:
            JSON response with session information:
            - is_active: boolean indicating if session is running
            - session_name: name of the current session
            - output_file: path to the output MF4 file
            - start_time: ISO formatted start timestamp
            - uptime_seconds: session duration in seconds
            - file_size_bytes: current output file size
            - can_channel: CAN interface channel name
            - can_bitrate: CAN bus bitrate
            - dbc_loaded: whether DBC is loaded
            - dbc_name: name of loaded DBC file
            
            Status codes:
            - 200: Status retrieved successfully
            - 500: Internal server error
        """
        try:
            status = session_manager.get_status()
            return jsonify(status), 200

        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            return jsonify({
                'error': 'Internal server error'
            }), 500

    @app.route('/api/dbc', methods=['GET'])
    def get_dbc_info():
        """
        Get information about the currently loaded DBC file.
        
        Returns:
            JSON response with DBC information:
            - loaded: boolean indicating if DBC is loaded
            - name: DBC file name (if loaded)
            - message_count: number of messages in database (if loaded)
            - signal_count: number of signals in database (if loaded)
            - message: descriptive message (if not loaded)
            
            Status codes:
            - 200: DBC is loaded (with info)
            - 404: No DBC is loaded
            - 500: Internal server error
        """
        try:
            if not dbc_manager.is_loaded():
                return jsonify({
                    'loaded': False,
                    'message': 'No DBC loaded'
                }), 404

            db_info = dbc_manager.get_database_info()

            return jsonify({
                'loaded': True,
                'name': db_info['name'],
                'message_count': db_info['message_count'],
                'signal_count': db_info['signal_count']
            }), 200

        except Exception as e:
            logger.error(f"Error getting DBC info: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/dbc', methods=['POST'])
    def upload_dbc():
        """
        Upload and load a new DBC file.
        
        Request: multipart/form-data with 'file' field containing .dbc file
        
        Returns:
            JSON response with operation result:
            - success: boolean indicating if DBC was loaded
            - message: name of loaded DBC (if successful)
            - error: error description (if failed)
            
            Status codes:
            - 200: DBC uploaded and loaded successfully
            - 400: Invalid file or parsing error
            - 500: Internal server error
        """
        try:
            # Validate file is present in request
            if 'file' not in request.files:
                return jsonify({
                    'success': False,
                    'error': 'No file provided'
                }), 400

            file = request.files['file']

            # Validate filename is not empty
            if file.filename == '':
                return jsonify({
                    'success': False,
                    'error': 'Empty filename'
                }), 400

            # Validate file extension
            if not file.filename.endswith('.dbc'):
                return jsonify({
                    'success': False,
                    'error': 'File must be a .dbc file'
                }), 400

            # Save file to DBC directory
            dbc_path = Path(log_config.dbc_dir) / file.filename
            file.save(str(dbc_path))

            # Load the DBC file
            success = dbc_manager.load_dbc(str(dbc_path))

            if success:
                return jsonify({
                    'success': True,
                    'message': f'Loaded DBC: {dbc_manager.dbc_name}'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to parse DBC file'
                }), 400

        except Exception as e:
            logger.error(f"Error uploading DBC: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Internal server error'
            }), 500

    @app.route('/api/logs', methods=['GET'])
    def list_logs():
        """
        List all MF4 log files in the output directory.
        
        Returns:
            JSON response with list of log files:
            - files: array of file objects, each containing:
                - name: filename
                - size: size in bytes
                - size_formatted: human-readable size (e.g., "12.3 MB")
                - modified: modification timestamp (Unix epoch)
            
            Files are sorted by modification time (newest first).
            
            Status codes:
            - 200: Files listed successfully (empty array if no files)
            - 500: Internal server error
        """
        try:
            log_dir = Path(log_config.output_dir)

            if not log_dir.exists():
                return jsonify({'files': []}), 200

            files = []
            for file_path in log_dir.glob('*.mf4'):
                stat = file_path.stat()
                files.append({
                    'name': file_path.name,
                    'size': stat.st_size,
                    'size_formatted': _format_size(stat.st_size),
                    'modified': stat.st_mtime
                })

            # Sort by modification time (newest first)
            files.sort(key=lambda x: x['modified'], reverse=True)

            return jsonify({'files': files}), 200

        except Exception as e:
            logger.error(f"Error listing logs: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/logs/<filename>', methods=['GET'])
    def download_log(filename: str):
        """
        Download a specific MF4 log file.
        
        Args:
            filename: Name of the log file to download
        
        Returns:
            File download or JSON error response:
            - On success: binary file download with proper Content-Disposition header
            - On error: JSON with error message
            
            Status codes:
            - 200: File download initiated
            - 400: Invalid filename (path traversal attempt)
            - 404: File not found
            - 500: Internal server error
        """
        try:
            # Security: prevent path traversal attacks
            if '..' in filename or '/' in filename or '\\' in filename:
                return jsonify({'error': 'Invalid filename'}), 400

            file_path = Path(log_config.output_dir).absolute() / filename

            if not file_path.exists():
                return jsonify({'error': 'File not found'}), 404

            return send_file(
                str(file_path),
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            logger.error(f"Error downloading log: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/logs/<filename>', methods=['DELETE'])
    def delete_log(filename: str):
        """
        Delete a specific MF4 log file.
        
        Args:
            filename: Name of the log file to delete
        
        Returns:
            JSON response with operation result:
            - success: boolean (only if successful)
            - message: confirmation message (only if successful)
            - error: error description (if failed)
            
            Status codes:
            - 200: File deleted successfully
            - 400: Invalid filename or attempting to delete active session file
            - 404: File not found
            - 500: Internal server error
            
        Note:
            Cannot delete the file of an active logging session.
        """
        try:
            # Security: prevent path traversal attacks
            if '..' in filename or '/' in filename or '\\' in filename:
                return jsonify({'error': 'Invalid filename'}), 400

            # Safety: prevent deletion of active session file
            if session_manager.is_active():
                current_file = Path(session_manager._output_file).name
                if filename == current_file:
                    return jsonify({
                        'error': 'Cannot delete active session file'
                    }), 400

            file_path = Path(log_config.output_dir) / filename

            if not file_path.exists():
                return jsonify({'error': 'File not found'}), 404

            file_path.unlink()
            logger.info(f"Deleted log file: {filename}")

            return jsonify({
                'success': True,
                'message': 'File deleted'
            }), 200

        except Exception as e:
            logger.error(f"Error deleting log: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500


def _format_size(size_bytes: int) -> str:
    """
    Format byte size into human-readable string.
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted string with appropriate unit (B, KB, MB, GB, TB, PB)
        
    Example:
        >>> _format_size(1536)
        "1.5 KB"
        >>> _format_size(5242880)
        "5.0 MB"
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"