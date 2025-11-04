from flask import request, jsonify, send_file, Flask
from pathlib import Path

from src.logging_config import get_logger
from src.utils.exceptions import (
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
    @app.route('/health', methods=['GET'])
    def health_check():
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
        try:
            if 'file' not in request.files:
                return jsonify({
                    'success': False,
                    'error': 'No file provided'
                }), 400

            file = request.files['file']

            if file.filename == '':
                return jsonify({
                    'success': False,
                    'error': 'Empty filename'
                }), 400

            if not file.filename.endswith('.dbc'):
                return jsonify({
                    'success': False,
                    'error': 'File must be a .dbc file'
                }), 400

            dbc_path = Path(log_config.dbc_dir) / file.filename
            file.save(str(dbc_path))

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
        try:
            if '..' in filename or '/' in filename or '\\' in filename:
                return jsonify({'error': 'Invalid filename'}), 400

            file_path = Path(log_config.output_dir) / filename

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
        try:
            if '..' in filename or '/' in filename or '\\' in filename:
                return jsonify({'error': 'Invalid filename'}), 400

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
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"