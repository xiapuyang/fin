#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fin.config import API_HOST, API_PORT

if __name__ == "__main__":
    uvicorn.run("fin.api:app", host=API_HOST, port=API_PORT, reload=False)
