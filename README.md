# Bolletta Sync

A web service for synchronizing and managing utility invoices across different Italian providers.

## Features

- REST API for invoice synchronization
- Support for multiple Italian utility providers
- Background task execution for syncing processes
- Automatic backup of invoices to Google Drive
- Creation of reminders for due dates in Google Tasks

## Requirements

- Python 3.13 or higher
- Provider credentials (configured via environment variables)

## Installation

Download the latest release for your platform:

- Windows: `bolletta-sync_windows.tar.gz`
- Linux: `bolletta-sync_linux.tar.gz`

The application is distributed as a single executable file, no additional installation steps required.

## Playwright Drivers

To install the Chromium drivers for Playwright, use the following command:

```bash
PLAYWRIGHT_BROWSERS_PATH=~/.playwright uvx playwright@1.56.0 install chromium
```

## Configuration

Create a file named `settings` in your home directory (e.g., `C:\Users\YourName\.bolletta-sync\settings` or `/home/YourName/.bolletta-sync/settings`).
The file must contain the following key-value pairs (adjust values as needed):

```plain text
CAPSOLVER_API_KEY=
FASTWEB_USERNAME=
FASTWEB_PASSWORD=
FASTWEB_CLIENT_CODE=
FASTWEB_ENERGIA_USERNAME=
FASTWEB_ENERGIA_PASSWORD=
UMBRA_ACQUE_USERNAME=
UMBRA_ACQUE_PASSWORD=
ENI_USERNAME=
ENI_PASSWORD=
```

## Usage

1. **Launch the API server**:
   ```bash
   python -m bolletta_sync.main
   ```
   The service will be available at `http://localhost:8000`. You can access the interactive API documentation at `http://localhost:8000/docs`.

2. **Check available providers**:
   `GET /providers`

3. **Trigger a synchronization**:
   `POST /sync`
   
   Request body example:
   ```json
   {
     "providers": ["fastweb", "eni"],
     "start_date": "2024-01-01",
     "end_date": "2024-02-01"
   }
   ```
