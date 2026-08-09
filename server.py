from mcp.server.fastmcp.server import FastMCP

mcp = FastMCP("Team-Opus MCP Server")

@mcp.tool()
def testing_tool(test_string: str) -> str:
    """
    A simple test tool that returns a string when called. 
    This can be used to verify that the MCP server is functioning correctly and that tools can be registered 
    and executed without issues.
    """
    return f'Received string: {test_string}'

if __name__ == "__main__":
    mcp.run(transport="stdio")