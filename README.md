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