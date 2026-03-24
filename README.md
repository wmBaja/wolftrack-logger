# Wolftrack-logger

Python Flask backend for logging CAN bus data from the Waveshare CANFD HAT to log files with DBC signal decoding.

## Quick Start

- **Python**: 3.7 or higher

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd wolftrack-logger

# Create virtual environment
python -m venv venv
```
Make sure to activate the venv before proceeding
```
# Install dependencies
pip install -r requirements.txt

# For development (includes testing tools)
pip install -r requirements-dev.txt
```

## Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_can_interface.py -v
```

### Run with Coverage

```bash
pytest --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```
---
## Project Structure

```
can_logger_backend/
├── src/
│   ├── api/
│   │   ├── routes.py          # Flask API endpoints
│   │   └── responses.py       # Response helpers
│   ├── app.py                 # Application entry point
│   ├── can_interface.py       # CAN bus interface
│   ├── config.py              # Configuration
│   ├── dbc_manager.py         # DBC file management
│   ├── logging_config.py      # Logging setup
│   ├── session_manager.py     # Session orchestration
│   └── utils.py               # Utilities & exceptions
├── tests/                     # Unit tests
├── dbc_files/                 # DBC database files
├── logs/                      # Log output files
├── app_logs/                  # Application logs
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

---

## Dependencies

### Core Libraries
- **python-can** - CAN bus interface
- **asammdf** - Log file creation
- **cantools** - DBC parsing and decoding
- **flask** - REST API framework
- **flask-cors** - CORS support

### Development
- **pytest** - Testing framework
- **pytest-cov** - Coverage reporting
- **pytest-mock** - Mocking utilities

## Contributing

2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
