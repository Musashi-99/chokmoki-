import uvicorn
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_server(port=8000, host="0.0.0.0"):
    print(f"Server running on http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    uvicorn.run(
        "api.index:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
