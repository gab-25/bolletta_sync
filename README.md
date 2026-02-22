# Bolletta Sync

A desktop application for synchronizing and managing utility invoices across different Italian providers.

## Features

- Date range selection for invoice synchronization
- Support for multiple Italian utility providers
- Real-time logging of synchronization progress
- User-friendly graphical interface
- Cross-platform support (Windows and Linux)
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

Create a file named `.bolletta_sync` in your home directory (e.g., `C:\Users\YourName\.bolletta_sync` or `/home/YourName/.bolletta_sync`).
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

1. Launch the application
2. Select the date range for bill synchronization
3. Check the providers you want to sync
4. Click the "SYNC" button to start the process
5. Monitor the progress in the output area
