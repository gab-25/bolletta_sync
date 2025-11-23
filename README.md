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

- Windows: `bolletta-sync_windows.exe`
- Linux: `bolletta-sync_linux`

The application is distributed as a single executable file, no additional installation steps required.

## Configuration

Create a folder named `.bolletta-sync` in your home directory (e.g., `C:\Users\YourName\.bolletta-sync` or `/home/YourName/.bolletta-sync`).
Inside this folder, place the following files:

1. `settings`: The configuration file for the application.

The `settings` file must contain the following key-value pairs (adjust values as needed):

```plain text
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