"""
ophix_creds.settings
~~~~~~~~~~~~~~~~~~~~
Default settings contributed by the ophix-creds plugin.
These are loaded non-destructively by ophix.settings.plugins —
values already set in base.py or .env take precedence.
"""

import os

SERVER_NAME = os.getenv("SERVER_NAME") or "credserver"
