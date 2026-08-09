# Team Opus — Garuda Robotics x NTU veNTUre

Prototype MCP-based system for allowing drone pilots to interact with Garuda Plex services through natural language.

The system uses Claude Desktop as the agent and MCP client, with custom MCP tools for route compliance, flight readiness, governance, and vision summarization.

## Architecture

```text
User
  ↓
Claude Desktop
(Agent + MCP Client)
  ↓
MCP Server
  ↓
Custom Tools
  ↓
API Client
  ↓
Garuda Plex APIs
```

## MCP Server + Claude Desktop Setup
1. Create and activate a Python virtual environment, then install the dependencies from `requirements.txt`.

   ```powershell
      python -m venv .venv
      .venv/Scripts/activate

      pip install -r requirements.txt
   ```
2. Check if the MCP server is running correctly by running:
  ```powershell
     mcp dev server.py
  ```  
  If it brings you to a website, then the server is running fine.
3. Install Claude Desktop for Windows (Link: https://claude.com/download), and sign in to your account.
4. Connect Claude Desktop to the MCP server.
   Update Claude Desktop's MCP config (claude_desktop_config.json) so it launches the server with the virtual environment Python executable. This config file can be accessible by Claude Desktop -> Settings -> Developer -> Edit Config:
   ```json
   {
     "mcpServers": {
       "garuda-drone": {
         "command": "C:\\PROJECT_PATH\\.venv\\Scripts\\python.exe",
         "args": [
           "C:\\PROJECT_PATH\\server.py"
         ]
       }
     }
   }
   ```
   After saving the config, fully quit and relaunch Claude Desktop so it reloads the MCP server.
5. Hover above the '+' symbol near the chatbox, if the label 'garuda-drone' appears, the MCP server has been integrated into     Claude Desktop.


