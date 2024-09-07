import sys

import asyncio
import json
import csv
from tenacity import retry, wait_exponential, stop_after_attempt
from better_proxy import Proxy
import aiohttp
from tabulate import tabulate
from data.config import THREADS
from utils import logger

output_lock = asyncio.Lock()


class ConsoleTableFormatter:
    def __init__(self):
        self.headers = ["#", "Wallet Address", "Total Tokens", "Status"]
        self.results = []
        self.table_top_printed = False
        self.column_widths = [3, 18, 12, 8]

    async def add_result(self, index, wallet, tokens, status):
        self.results.append([index, wallet, tokens, status])
        await self.print_table_row()

    async def print_table_row(self):
        async with output_lock:
            if not self.table_top_printed:
                print(self.format_row(self.headers, is_header=True))
                self.table_top_printed = True

            new_row = self.results[-1]
            print(self.format_row(new_row))

            sys.stdout.flush()

    def format_row(self, row, is_header=False):
        formatted_row = []
        for i, (item, width) in enumerate(zip(row, self.column_widths)):
            if i == 0 or i == 2:
                formatted_item = str(item).rjust(width)
            else:
                formatted_item = str(item).ljust(width)
            formatted_row.append(formatted_item)

        if is_header:
            return f"| {' | '.join(formatted_row)} |"
        else:
            return f"| {' | '.join(formatted_row)} |"


class AirdropAllocator:
    def __init__(self, wallet_address: str, proxy: str = None, index: int = 0, max_concurrent_requests: int = 5):
        self.wallet_address = wallet_address
        self.masked_wallet = f"{self.wallet_address[:6]}...{self.wallet_address[-6:]}"
        self.proxy = proxy and Proxy.from_str(proxy).as_url
        self.index = index
        self.base_url = 'https://api.getgrass.io/airdropAllocations'
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://www.grassfoundation.io',
            'priority': 'u=1, i',
            'referer': 'https://www.grassfoundation.io/',
            'sec-ch-ua': '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        }
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.results_table = []
        self.table_formatter = table_formatter

    @retry(wait=wait_exponential(min=2, max=7), stop=stop_after_attempt(7))
    async def fetch_airdrop_allocation(self):
        async with self.semaphore:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(f'{self.base_url}?input=%7B%22walletAddress%22:%22{self.wallet_address}%22%7D',
                                       headers=self.headers, proxy=self.proxy, verify_ssl=False) as response:

                    data = await response.json()
                    assert data.get('result')

                    return data

    def calculate_totals(self, data):
        points = data.get('result', {}).get('data', {})
        total = sum(points.values())
        points['all'] = total
        return points

    def beautify_and_log(self, data, log_filename='airdrop_log.json'):
        with open(log_filename, 'a') as log_file:
            json.dump(data, log_file, indent=4)
            log_file.write('\n')

    def save_to_csv(self, data, filename='airdrop_allocation.csv'):
        result_data = data.get('result', {}).get('data', {})
        if not result_data:
            return

        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Tier', 'Amount'])

            for key, value in result_data.items():
                writer.writerow([key, value])

    async def format_console_output(self, data, status):
        global all_tokens

        total_tokens = data.get('all', 0)
        all_tokens += total_tokens

        if self.table_formatter:
            await self.table_formatter.add_result(self.index, self.masked_wallet, total_tokens, status)
        else:
            print(f"{self.index} | {self.masked_wallet} | {total_tokens} | {status}")

    async def process_allocation(self, log_filename='airdrop_log.json'):
        try:
            data = await self.fetch_airdrop_allocation()
            totals = self.calculate_totals(data)

            if data.get('result', {}).get("data") is None:
                await self.format_console_output({}, "Error")
                return

            if any('_sybil' in key for key in totals):
                status = "Sybil"
                sybils.append(self.wallet_address)
            else:
                status = "Eligible"

            await self.format_console_output(totals, status)
            self.beautify_and_log(data, log_filename)
            self.save_to_csv(data)
        except Exception as e:
            await self.format_console_output({}, "Error")

async def read_file_lines(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

async def print_table_headers():
    headers = ["#", "Wallet Address", "Total Tokens", "Status"]
    async with output_lock:
        print(tabulate([], headers=headers, tablefmt="grid"))

async def main():
    path = "data"
    wallet_addresses = await read_file_lines(f'{path}/wallets.txt')

    if not wallet_addresses:
        logger.info("No wallet addresses found!")
        return

    proxies = await read_file_lines(f'{path}/proxies.txt')

    max_concurrent_requests = THREADS
    tasks = []

    print("+-----+------------------+----------------+----------+")

    for i, wallet in enumerate(wallet_addresses):
        proxy = proxies[i % len(proxies)] if proxies else None
        allocator = AirdropAllocator(wallet_address=wallet, proxy=proxy, index=i+1, max_concurrent_requests=max_concurrent_requests)
        tasks.append(asyncio.create_task(allocator.process_allocation()))

    await asyncio.gather(*tasks)

    with open("logs/sybils.txt", "w") as f:
        f.write("\n".join(sybils))

    print("+-----+------------------+----------------+----------+")
    logger.success(f"Total tokens: {all_tokens}")

if __name__ == '__main__':
    all_tokens = 0
    sybils = []
    table_formatter = ConsoleTableFormatter()

    print("Starting Airdrop Allocator...")
    print("IF ERRORS OCCUR - CHANGE PROXY OR wallet is INVALID OR UNELIGIBLE\n")

    asyncio.run(main())
