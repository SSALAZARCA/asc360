
import httpx
import asyncio

async def test_header_none():
    url = "http://localhost:8000/api/v1/vehicles/NOI82G"
    async with httpx.AsyncClient() as client:
        # Case 1: Literal None
        headers1 = {"X-Tenant-ID": None}
        try:
            res1 = await client.get(url, headers=headers1)
            print(f"Header None -> Status: {res1.status_code}, Text: {res1.text[:50]}")
        except Exception as e:
            print(f"Header None -> Error: {e}")

        # Case 2: String "None"
        headers2 = {"X-Tenant-ID": "None"}
        res2 = await client.get(url, headers=headers2)
        print(f"Header 'None' -> Status: {res2.status_code}, Text: {res2.text[:50]}")

        # Case 3: Missing header (The one that worked in check_api.py)
        res3 = await client.get(url)
        print(f"No Header -> Status: {res3.status_code}, Text: {res3.text[:50]}")

if __name__ == "__main__":
    asyncio.run(test_header_none())
