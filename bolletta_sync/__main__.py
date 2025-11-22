import argparse
import asyncio
from datetime import date

from bolletta_sync.main import main, Provider

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sync invoices from providers')
    parser.add_argument('--start_date', type=str, help='Start date in format YYYY-MM-DD')
    parser.add_argument('--end_date', type=str, help='End date in format YYYY-MM-DD')
    parser.add_argument('--providers', nargs='+', type=Provider, help='List of providers to sync')
    args = parser.parse_args()

    if args.start_date:
        args.start_date = date.fromisoformat(args.start_date)
    if args.end_date:
        args.end_date = date.fromisoformat(args.end_date)

    asyncio.run(main(providers=args.providers, start_date=args.start_date, end_date=args.end_date))
