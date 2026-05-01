# Wolftrack Logger

Python Flask backend for logging CAN bus data from the Waveshare CANFD HAT to log files

## Local Development (With `uv`)

This project uses `uv` for dependency management and environment isolation.

### Prerequisites
- Install `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Setup

```bash
# Clone the repository
git clone https://github.com/wmBaja/wolftrack-logger.git
cd wolftrack-logger

# Sync dependencies and create the virtual environment
uv sync

# Run the application locally
uv run src/app.py
```

### Testing
Currently testing is not enforced and coverage is low. But if you want to run tests:

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

---

## Raspberry Pi Deployment

We have built a automated deployment system to install and update `wolftrack-logger` on a Raspberry Pi 4 equipped with a Waveshare CAN-FD HAT and a DS3231 RTC.

### 1. Initial Setup (Fresh Pi)
1. Flash your Raspberry Pi with the latest OS (Trixie or Bookworm) and connect it to your home internet.
2. From your **host computer** (Windows/Mac/Linux), open a terminal in this project directory and run:
   ```bash
   python scripts/deploy.py pi@<pi-ip-address> --setup
   ```
   *The script will securely transfer the codebase to the Pi, install all system packages, configure the CAN/RTC boot overlays, create the systemd service, and finally convert the Pi into an offline Access Point named `Wolftrack`.*

### 2. Pushing Updates (Offline)
1. Connect your host computer to the `Wolftrack` Wi-Fi network broadcasted by the Pi.
2. Make your code changes locally.
3. Run the deploy script *without* the setup flag:
   ```bash
   python scripts/deploy.py pi@<pi-ip-address>
   ```
   *This uses standard tools to push only the updated code over the local network and restart the logger service instantly. No internet connection is needed.*

---

## Raspberry Pi Network Management

Once the Pi is deployed, it acts as an offline Access Point. If you need to switch it back to the internet (e.g., to install a system update via `apt`), you can use the provided utility scripts directly on the Pi over SSH:

- **Switch to Client (Internet):**
  ```bash
  sudo ./scripts/switch_to_client.sh "YourHomeSSID" "YourPassword"
  ```
  *(If you omit the SSID/Password, it will simply turn off the AP and attempt to auto-connect to any known saved networks).*

- **Switch to Access Point:**
  ```bash
  sudo ./scripts/switch_to_ap.sh
  ```

---

## Project Structure

```
wolftrack-logger/
├── src/
│   ├── api/               # Flask API endpoints
│   ├── app.py             # Application entry point
│   ├── can_interface.py   # CAN bus interface
│   ├── config.py          # Configuration
│   ├── dbc_manager.py     # DBC file management
│   ├── logging_config.py  # Logging setup
│   ├── session_manager.py # Session orchestration
│   └── utils/             # Utilities & helpers
├── scripts/               # Deployment and network management scripts
│   ├── deploy.py          # Cross-platform deployment script
│   ├── setup_pi.sh        # Initial Pi setup script
│   ├── bring_can_up.sh    # Dynamic CAN interface configuration
│   └── switch_to_*.sh     # Network toggling scripts
├── tests/                 # Unit tests
├── pyproject.toml         # Project dependencies (uv)
└── .env.example           # Environment variable templates
```
