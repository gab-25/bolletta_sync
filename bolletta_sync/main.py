import logging
from datetime import date, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from bolletta_sync.sync import Provider, SyncParams, main, logger

app = FastAPI(
    title="Bolletta Sync API",
    description="Web service to sync invoices from various providers to Google Drive/Tasks",
    version="0.8.0",
)


class SyncRequest(BaseModel):
    providers: Optional[List[Provider]] = Field(
        default=None, description="List of providers to sync. If null, all providers will be synced."
    )
    start_date: Optional[date] = Field(
        default=None, description="Start date for syncing (YYYY-MM-DD). Defaults to 10 days ago."
    )
    end_date: Optional[date] = Field(default=None, description="End date for syncing (YYYY-MM-DD). Defaults to today.")


class SyncResponse(BaseModel):
    message: str
    status: str


@app.get("/")
async def root():
    return {"message": "Bolletta Sync API is running", "version": "0.8.0"}


@app.get("/providers")
async def get_providers():
    return {"providers": [p.value for p in Provider]}


@app.post("/sync", response_model=SyncResponse)
async def trigger_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Triggers the synchronization process as a background task.
    """
    start_date = request.start_date if request.start_date else date.today() - timedelta(days=10)
    end_date = request.end_date if request.end_date else date.today()
    providers = request.providers if request.providers else list(Provider)

    # Basic validation before starting background task
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    # Run the main sync process in the background
    background_tasks.add_task(main, providers, start_date, end_date)

    return SyncResponse(
        message=f"Sync started for {len(providers)} providers from {start_date} to {end_date}", status="accepted"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
