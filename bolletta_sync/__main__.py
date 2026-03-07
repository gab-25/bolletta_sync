import uvicorn
from bolletta_sync.main import app

if __name__ == "__main__":
    # This allows the package to be run using `python -m bolletta_sync`
    uvicorn.run("bolletta_sync.main:app", host="0.0.0.0", port=8000, reload=False)
