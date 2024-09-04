import asyncio
import httpx
import json
import csv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from better_proxy import Proxy

from data.config import THREADS
from utils import logger


class AirdropAllocator:
    def __init__(self, wallet_address: str, proxy: str = None, max_concurrent_requests: int = 5):
        self.wallet_address = wallet_address
        self.proxy = proxy and Proxy.from_str(proxy).as_url

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

    @retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(httpx.HTTPError))
    async def fetch_airdrop_allocation(self):
        async with self.semaphore:
            async with httpx.AsyncClient(proxy=self.proxy, verify=False) as client:
                response = await client.get(f'{self.base_url}?input=%7B%22walletAddress%22:%22{self.wallet_address}%22%7D', headers=self.headers)
                response.raise_for_status()
                return response.json()

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
            logger.warning("No data found to save.")
            return

        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Tier', 'Amount'])

            for key, value in result_data.items():
                writer.writerow([key, value])

    def format_console_output(self, wallet, data):
        global all_tokens

        masked_wallet = f"{wallet[:6]}....{wallet[-6:]}"
        total_tokens = data.get('all', 0)
        all_tokens += total_tokens

        # Build the string for epochs
        epoch_info = " | ".join(
            [f"{key.replace('_user', '').title()}: {value}" for key, value in data.items() if "epoch" in key])

        # Check for the presence of `_sybil`
        if any('_sybil' in key for key in data):
            logger.warning(f"SYBIL | {masked_wallet} Tokens: {total_tokens} | {epoch_info}")
        else:
            logger.success(f"{masked_wallet} Tokens: {total_tokens} | {epoch_info}")

    async def process_allocation(self, log_filename='airdrop_log.json'):
        try:
            data = await self.fetch_airdrop_allocation()
            totals = self.calculate_totals(data)
            self.format_console_output(self.wallet_address, totals)
            self.beautify_and_log(data, log_filename)
            self.save_to_csv(data)
        except Exception as e:
            logger.error(f"An error occurred for {self.wallet_address}: {e}")

async def read_file_lines(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

async def main():
    path = "data"
    wallet_addresses = await read_file_lines(f'{path}/wallets.txt')

    if not wallet_addresses:
        logger.info("No wallet addresses found!")
        return

    proxies = await read_file_lines(f'{path}/proxies.txt')

    max_concurrent_requests = THREADS
    tasks = []

    for i, wallet in enumerate(wallet_addresses):
        proxy = proxies[i % len(proxies)] if proxies else None
        allocator = AirdropAllocator(wallet_address=wallet, proxy=proxy, max_concurrent_requests=max_concurrent_requests)
        tasks.append(asyncio.create_task(allocator.process_allocation()))

    await asyncio.gather(*tasks)

    logger.success(f"Total tokens: {all_tokens}")

if __name__ == '__main__':
    all_tokens = 0

    asyncio.run(main())
