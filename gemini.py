import os
import json
import asyncio

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
import google.generativeai as genai
from google.generativeai import types

load_dotenv()


async def main():
    # 1. Configure Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in your environment or .env")
    genai.configure(api_key=api_key)

    # 2. Start the MCP server (same as Claude does)
    project_root = os.path.dirname(os.path.abspath(__file__))
    server_params = StdioServerParameters(
        command="python3",
        args=["-m", "tatc_mcp.server"],
        env={**os.environ, "PYTHONPATH": project_root + os.pathsep + os.environ.get("PYTHONPATH", "")},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 3. Fetch tools from MCP server
            tools_response = await session.list_tools()
            mcp_tools = tools_response.tools

            def strip_defaults(schema):
                if isinstance(schema, dict):
                    return {
                        k: strip_defaults(v)
                        for k, v in schema.items()
                        if k != "default"
                    }
                if isinstance(schema, list):
                    return [strip_defaults(x) for x in schema]
                return schema

            function_declarations = []
            for tool in mcp_tools:
                input_schema = getattr(tool, "inputSchema", {
                    "type": "object",
                    "properties": {},
                    "required": [],
                })
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description or f"Tool: {tool.name}",
                        parameters=strip_defaults(input_schema),
                    )
                )

            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                tools=[function_declarations],
            )

            # 4. Run a prompt through Gemini with tool calling
            prompt = "Give me the ISS ground track for the next 10 minutes at 10 sec steps."
            chat = model.start_chat()
            response = chat.send_message(prompt)

            def get_function_calls(resp):
                if not (resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts):
                    return []
                return [
                    p for p in resp.candidates[0].content.parts
                    if hasattr(p, "function_call") and p.function_call
                ]

            for _ in range(10):
                calls = get_function_calls(response)
                if not calls:
                    # No tool calls; just print Gemini's answer
                    print("Gemini response:", response.text)
                    return

                for part in calls:
                    fc = part.function_call
                    name = fc.name
                    args = dict(fc.args) if hasattr(fc, "args") else {}
                    # 5. Call MCP tool
                    tool_result = await session.call_tool(name, args)
                    text = tool_result.content[0].text if tool_result.content else ""
                    print(f"Tool {name} result (truncated):", text[:500])

                    # Feed result back to Gemini if you want further reasoning
                    response = chat.send_message({
                        "function_response": {
                            "name": name,
                            "response": {"result": text},
                        }
                    })

if __name__ == "__main__":
    asyncio.run(main())