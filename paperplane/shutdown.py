"""Process shutdown support for the local Paperplane UI."""

from __future__ import annotations

import os
import threading

SHUTDOWN_DELAY_SECONDS = 0.75
TAB_LISTENER_HTML = """
<script>
(() => {
  if (window.__paperplaneShutdownChannel) return;
  const channel = new BroadcastChannel("paperplane-shutdown");
  channel.onmessage = (event) => {
    if (event.data === "stop-and-clear") {
      window.location.replace("about:blank");
    }
  };
  window.__paperplaneShutdownChannel = channel;
})();
</script>
"""
SHUTDOWN_HTML = """
<script>
(() => {
  const channel = window.__paperplaneShutdownChannel
    || new BroadcastChannel("paperplane-shutdown");
  channel.postMessage("stop-and-clear");
  window.setTimeout(() => window.location.replace("about:blank"), 150);
})();
</script>
"""


def schedule_process_exit(delay_seconds: float = SHUTDOWN_DELAY_SECONDS) -> threading.Timer:
    """Exit successfully after pending Streamlit deltas reach the browser."""
    timer = threading.Timer(delay_seconds, os._exit, args=(0,))
    timer.daemon = True
    timer.start()
    return timer
