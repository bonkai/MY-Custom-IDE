# run.py  – minimal launcher
import threading, webview, app   # app is your Flask module

# Start Flask in the background so the GUI loop can take over
threading.Thread(target=lambda: app.app.run(), daemon=True).start()

webview.create_window(
    "Chat-IDE",
    "http://127.0.0.1:5000/",
    width=1200,
    height=800,
)

webview.start()          # <- the line that actually shows the window