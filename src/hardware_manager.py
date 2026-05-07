import logging
from typing import Optional

from config import HardwareConfig
from session_manager import SessionManager

logger = logging.getLogger(__name__)

class HardwareManager:
    """Manages physical hardware components (buttons, LEDs) using gpiozero."""

    def __init__(self, config: HardwareConfig, session_manager: SessionManager):
        self.config = config
        self.session_manager = session_manager
        
        self.button = None
        self.led = None

        if not self.config.enabled:
            logger.info("Hardware controls are disabled in configuration.")
            return

        try:
            from gpiozero import Button, LED
            from gpiozero.exc import BadPinFactory
            
            # Initialize Button and LED
            logger.info(f"Initializing hardware controls (Button Pin: {self.config.button_pin}, LED Pin: {self.config.led_pin})")
            
            # bounce_time prevents false double-clicks
            self.button = Button(self.config.button_pin, bounce_time=0.2)
            self.led = LED(self.config.led_pin)

            # Bind the button press event
            self.button.when_pressed = self.toggle_logging
            
            # Register callbacks to keep LED in sync with session state (API or otherwise)
            self.session_manager.register_on_start(self.set_led_on)
            self.session_manager.register_on_stop(self.set_led_off)

            # Initialize LED state to current session state
            if self.session_manager.is_active():
                self.set_led_on()
            else:
                self.set_led_off()

            logger.info("Hardware controls successfully initialized.")

        except ImportError:
            logger.warning("gpiozero is not installed. Hardware controls will be disabled.")
        except Exception as e:
            # We catch general exceptions (like BadPinFactory) when running on non-Pi hardware
            logger.warning(f"Failed to initialize hardware controls: {e}. Are you running on a Raspberry Pi?")

    def toggle_logging(self) -> None:
        """Called when the physical button is pressed."""
        logger.info("Physical button pressed.")
        
        # Determine current state and toggle
        if self.session_manager.is_active():
            logger.info("Session is active. Attempting to stop logging via hardware button...")
            success, msg = self.session_manager.stop()
            if not success:
                logger.error(f"Hardware button failed to stop session: {msg}")
        else:
            logger.info("No active session. Attempting to start logging via hardware button...")
            success, msg = self.session_manager.start()
            if not success:
                logger.error(f"Hardware button failed to start session: {msg}")

    def set_led_on(self) -> None:
        """Turns the status LED on."""
        if self.led:
            self.led.on()

    def set_led_off(self) -> None:
        """Turns the status LED off."""
        if self.led:
            self.led.off()

    def cleanup(self) -> None:
        """Clean up hardware resources."""
        if self.button:
            self.button.close()
            self.button = None
        if self.led:
            self.led.close()
            self.led = None
