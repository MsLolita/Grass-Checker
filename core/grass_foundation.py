import aiohttp
from fake_useragent import UserAgent
from tenacity import retry, wait_exponential, stop_after_attempt
from better_proxy import Proxy

class GrassFoundationChecker:
    def __init__(self, wallet_address: str, proxy: str = None):
        self.wallet_address = wallet_address
        self.proxy = proxy and Proxy.from_str(proxy).as_url
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://www.grassfoundation.io',
            'referer': 'https://www.grassfoundation.io/',
            'user-agent': UserAgent().random,
        }

    async def check_v2(self):
        url = 'https://api.getgrass.io/airdropAllocationsV2'
        return await self.check_allocation(url)

    async def check_final(self):
        url = 'https://api.getgrass.io/zvTlZ8PRouKKGTGNzg4k'
        return await self.check_allocation(url)

    @retry(wait=wait_exponential(min=1, max=2), stop=stop_after_attempt(3))
    async def check_allocation(self, url: str = None):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(f'{url}?input=%7B%22walletAddress%22:%22{self.wallet_address}%22%7D',
                                   headers=self.headers, proxy=self.proxy, verify_ssl=False) as response:
                data = await response.json()
                assert data.get('result')
                return data

    @staticmethod
    def calculate_totals(data):
        points = data.get('result', {}).get('data', {})
        total = sum(points.values())
        points['all'] = total
        return points

