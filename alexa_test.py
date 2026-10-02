from fastmcp import FastMCP

mcp = FastMCP("CareLoop")

@mcp.tool()
def hello():
    """Check whether CareLoop is connected."""
    return "CareLoop is connected and working."

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)