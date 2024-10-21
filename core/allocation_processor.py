import json
import csv
from .grass_foundation import GrassFoundationChecker

class AllocationProcessor:
    def __init__(self, wallet_address: str, proxy: str = None, index: int = 0):
        self.wallet_address = wallet_address
        self.masked_wallet = f"{self.wallet_address[:6]}...{self.wallet_address[-6:]}"
        self.index = index
        self.checker = GrassFoundationChecker(wallet_address, proxy)

    @staticmethod
    def beautify_and_log(data, log_filename='airdrop_log.json'):
        with open(log_filename, 'a') as log_file:
            json.dump(data, log_file, indent=4)
            log_file.write('\n')

    def save_to_csv(self, data, filename='airdrop_allocation.csv'):
        result_data = data.get('result', {}).get('data', {})
        if not result_data:
            return

        try:
            with open(filename, 'r') as file:
                existing_wallets = set(next(csv.reader(file)))
        except FileNotFoundError:
            existing_wallets = set()

        if self.wallet_address not in existing_wallets:
            with open(filename, mode='a', newline='') as file:
                csv.writer(file).writerow([self.wallet_address, result_data.get('all', 0)])

    async def process_allocation(self, table_formatter, log_filename='airdrop_result'):
        try:
            data = await self.checker.check_final()
            totals = self.checker.calculate_totals(data)

            if data.get('result', {}).get("data") is None:
                table_formatter.add_result(self.index, self.masked_wallet, 0, "Error")
                return 0

            total_tokens = round(totals.get('all', 0), 2)

            status = "Sybil" if any('_sybil' in key for key in totals) else "Eligible"
            with open(f"logs/{status.lower()}s.txt", "a") as f:
                f.write(f"{self.wallet_address}\n")

            table_formatter.add_result(self.index, self.masked_wallet, total_tokens, status)
            self.beautify_and_log(data, f"logs/{log_filename}.json")
            self.save_to_csv(data, f"logs/{log_filename}.csv")
            return total_tokens
        except Exception:
            table_formatter.add_result(self.index, self.masked_wallet, 0, "Error")
            return 0
