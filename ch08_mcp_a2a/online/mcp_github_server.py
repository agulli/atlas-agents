from mcp.server.fastmcp import FastMCP
import os
from github import Github

# A FastMCP server exposing authenticated Github actions to an agent securely
mcp = FastMCP("GithubLocal")
g = Github(os.environ.get("GITHUB_TOKEN"))

@mcp.tool()
def search_repos(query: str) -> list[str]:
    """Search for Github repositories."""
    repos = g.search_repositories(query)
    return [repo.full_name for repo in repos[:5]]

if __name__ == "__main__":
    mcp.run() # Starts the stdio interface that agents connect to
