import asyncio
from rich.console import Console
from rich.table import Table
from rich.live import Live

from data.config import THREADS
from utils import logger
from core.allocation_processor import AllocationProcessor

class ConsoleTableFormatter:
    def __init__(self):
        self.headers = ["#", "Wallet Address", "Total Tokens", "Status"]
        self.table = Table(title="\nAirdrop Allocation Results")
        for header in self.headers:
            self.table.add_column(header, style="cyan", justify="center")
        self.console = Console()

    def add_result(self, index, wallet, tokens, status):
        self.table.add_row(str(index), wallet, str(tokens), status, style="bright_green")

async def read_file_lines(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

async def process_wallet(wallet, proxy, index, table_formatter, semaphore):
    async with semaphore:
        processor = AllocationProcessor(wallet, proxy, index)
        return await processor.process_allocation(table_formatter)

async def main():
    wallet_addresses = await read_file_lines('data/wallets.txt')
    if not wallet_addresses:
        logger.info("No wallet addresses found!")
        return

    logger.info(f"Total wallets: {len(wallet_addresses)}")

    proxies = await read_file_lines('data/proxies.txt')
    table_formatter = ConsoleTableFormatter()

    semaphore = asyncio.Semaphore(THREADS)
    
    all_tokens = 0

    tasks = [
        process_wallet(
            wallet,
            proxies[i % len(proxies)] if proxies else None,
            i+1,
            table_formatter,
            semaphore
        )
        for i, wallet in enumerate(wallet_addresses)
    ]

    with Live(table_formatter.table, refresh_per_second=4):
        for task in asyncio.as_completed(tasks):
            result = await task
            all_tokens += result

    print("\n")
    logger.success(f"Total: {all_tokens} $GRASS / {all_tokens * 1.5} $")


if __name__ == '__main__':
    console = Console()
    console.print("Starting Airdrop Allocator...", style="bold green")
    console.print("IF ERRORS OCCUR - CHANGE PROXY OR wallet is INVALID OR UNELIGIBLE\n", style="bold yellow")

    asyncio.run(main())
