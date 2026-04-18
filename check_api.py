
import httpx
import asyncio

async def check_vehicle():
    url = "http://localhost:8000/api/v1/vehicles/NOI82G"
    headers = {"X-Tenant-ID": "c9a40552-3eb6-4cb4-bfff-6aacaead3ca7"} # Try with fake tenant
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(res.json())
        else:
            print(res.text)

        # Try without tenant
        res_global = await client.get(url)
        print(f"Global Status: {res_global.status_code}")
        if res_global.status_code == 200:
            print(res_global.json())
        else:
            print(res_global.text)

if __name__ == "__main__":
    asyncio.run(check_vehicle())
