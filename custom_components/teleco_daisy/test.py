import asyncio
import aiohttp
from teleco_daisy import TelecoDaisy


async def main():
    async with aiohttp.ClientSession() as session:
        api = TelecoDaisy(session, "drd@interia.pl", "wshw!2MvNWq")
        await api.login(api.email, api.password)

        installations = await api.get_account_installation_list()
        print("Installations:", installations)

        # Use the first installation object directly
        installation = installations[0]
        result = await api.get_room_list(installation)
        print("Is active:", result)


if __name__ == "__main__":
    asyncio.run(main())
