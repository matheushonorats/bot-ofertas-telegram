import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "2")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Mute http access logs to avoid clutter
        return

def start_health_server(port=None):
    if port is None:
        port = int(os.environ.get("PORT", "0"))
    
    if port <= 0:
        return

    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"[Web Server] Servidor de monitoramento ativo na porta {port} (Necessario para o Render)")
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
    except Exception as e:
        print(f"[Web Server] Erro ao iniciar servidor web: {e}")
