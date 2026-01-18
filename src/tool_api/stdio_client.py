from __future__ import annotations
import json
import subprocess
import threading
from typing import Dict, Any, Optional

class StdioJsonRpcClient:
    """
    Minimal JSON-RPC 2.0 client over stdio
    -send one JSON object per line to server stdin
    - read one JSON object per line from server stdout
    Assume sequential calls (one outstanding request at a time)
    """
    def __init__(self, server_module: str = "src.tool_server_stdio.server"):
        # start: python -m src.tool_server_stdio.server
        self.proc = subprocess.Popen(
            ["python", "-m", server_module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._lock = threading.lock()
        self._next_id = 1
        
    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
                
        except Exception:
            pass
        
        try:
            self.proc.terminate()
        except Exception:
            pass
    
    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            
            req = {"jsonrpc":"2.0", "id": rid, "method": method, "params":params}
            
            assert self.proc.stdin is not None
            assert self.proc.stdout is not None
            
            self.proc.stdin.write(json.dumps(req)+"\n")
            self.proc.stdin.flush()
            
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Tool server closed stdout unexpectedly.")
            
            resp = json.loads(line)
            if "error" in resp and resp["error"] is not None:
                raise RuntimeError(f"RPC error: {resp["error"]}")
            
    def list_tools(self) -> Dict[str, Any]:
        return self._rpc("tools.list", {})
    
    def call(self, tool_name: str, args:Dict[str, Any]) -> Dict[str, Any]:
        return self._rpc("tools.call", {"name": tool_name, "args":args})
        
    
        
    