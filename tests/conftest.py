"""Test settings: no artificial "Ryde Support is typing" pause."""
import os

os.environ.setdefault("DEMO_TYPING_DELAY", "0")
