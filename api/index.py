import json
import asyncio
from http.server import BaseHTTPRequestHandler
from typing import Dict, Any
from src.database.connection import db
from src.cqrs.router import CQRSRouter
from src.plugins.logger import logger


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            operation = data.get("operation")
            operation_type = data.get("type")
            params = data.get("params", {})
            
            if not operation:
                self._send_response(400, {"error": "Operation is required"})
                return
            
            if operation_type not in ["query", "mutation"]:
                self._send_response(400, {"error": "Type must be 'query' or 'mutation'"})
                return
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                if operation_type == "query":
                    result = loop.run_until_complete(CQRSRouter.execute_query(operation, params))
                else:
                    result = loop.run_until_complete(CQRSRouter.execute_mutation(operation, params))
                
                self._send_response(200, result)
            finally:
                loop.close()
            
        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            self._send_response(400, {"error": str(e)})
        except Exception as e:
            logger.error(f"Server error: {str(e)}")
            self._send_response(500, {"error": "Internal server error"})
    
    def _send_response(self, status_code: int, data: Dict[str, Any]):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def log_message(self, format, *args):
        pass

