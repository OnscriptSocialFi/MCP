import asyncio
from fastmcp import Client


client=Client("./server.py");


async def main():
    async with client:
        print("Connected:",client.is_connected())

        tools = await client.list_tools()
        print("Available tools:", [t.name for t in tools])

        res= await client.call_tool("email_sign_in",{"email":"lawuche29@gmail.com"}) 
        print(res.data)

        res= await client.call_tool("email_sign_up",{"email":"lawuche29@gmail.com"}) 
        print(res.data)



if __name__ == "__main__":
    asyncio.run(main())

