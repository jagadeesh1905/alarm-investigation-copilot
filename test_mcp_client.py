
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server.py"],
        env={
            **os.environ,
            "ALARM_API_BASE_URL": "http://127.0.0.1:8000",
            "ALARM_API_TOKEN": "demo-token",
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            response = await session.list_tools()

            print("Available MCP tools:")
            for tool in response.tools:
                print(f"- {tool.name}: {tool.description}")
            

            print("\nTesting get_asset_metadata...")
            result = await session.call_tool(
                "get_asset_metadata",
                arguments={"asset_id": "AST-203"},
            )

            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)



            print("\nTesting search_assets...")
            result = await session.call_tool(
                "search_assets",
                arguments={"query": "AST-203"},
            )

            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)
            


                        
            print("\nTesting list_alarms...")
            result = await session.call_tool(
                "list_alarms",
                arguments={"status": "active"},
            )

            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)

            for name, args in [
                ("score_alarm_priority", {"alarm_id": "ALM-006"}),          # the fixed bug
                ("get_operator_recommendations", {"alarm_id": "ALM-006"}),
                ("correlate_alarms", {"asset_id": "AST-504"}),
                ("get_alarm", {"alarm_id": "ALM-999"}),                       # expect alarm_not_found
                ("get_alarm", {"alarm_id": "../etc"}),                        # expect validation error
            ]:
                print(f"\n{name}")
                result = await session.call_tool(name, arguments=args)
                print("isError:", result.isError)
                for item in result.content:
                    if hasattr(item, "text"):
                        print(item.text[:400])           
            print("\nTesting get_alarm_summary...")
            result = await session.call_tool(
                "get_alarm_summary",
                arguments={"asset_ids": ["AST-203"]},
            )
            print("isError:", result.isError)
            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text[:1500])

            print("\nTesting get_alarm_trends...")
            result = await session.call_tool(
                "get_alarm_trends",
                arguments={"asset_ids": ["AST-203"]},
            )
            print("isError:", result.isError)
            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text[:1500])
            
            print("\nTesting search_procedures...")
            result = await session.call_tool(
                "search_procedures",
                arguments={
                    "query": "What should be investigated for high bearing temperature?",
                    "top_k": 2,
                },
            )

            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)




if __name__ == "__main__":
    asyncio.run(main())
