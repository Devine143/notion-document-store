"""
Main MCP server for the Notion Document Store.

This module implements the Model Context Protocol (MCP) server that provides
three core tools for document management:
1. add_document - Create new documents in Notion
2. search_documents - Search for documents with filtering
3. get_document - Retrieve specific documents by ID
"""
import logging
import os
import asyncio
import time
from typing import List, Dict, Any
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from enum import Enum

from .modules.notion_client import NotionClient, NotionAPIError
from .modules.data_types import (
    AddDocumentRequest, 
    SearchDocumentsRequest, 
    GetDocumentRequest,
    DocumentCategory,
    ErrorResponse,
    SuccessResponse
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('notion_doc_store.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Environment variables
NOTION_API_SECRET = os.getenv("NOTION_INTERNAL_INTEGRATION_SECRET")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_API_VERSION = os.getenv("NOTION_API_VERSION", "2022-06-28")

# Validate required environment variables
if not NOTION_API_SECRET:
    raise ValueError("NOTION_INTERNAL_INTEGRATION_SECRET environment variable is required")
if not NOTION_DATABASE_ID:
    raise ValueError("NOTION_DATABASE_ID environment variable is required")


class DocumentTools(str, Enum):
    """Available MCP tools for document management."""
    ADD_DOCUMENT = "add_document"
    SEARCH_DOCUMENTS = "search_documents"
    GET_DOCUMENT = "get_document"


# Global metrics tracking
server_metrics = {
    "start_time": time.time(),
    "requests_total": 0,
    "requests_success": 0,
    "requests_failed": 0,
    "tools_called": {
        DocumentTools.ADD_DOCUMENT: 0,
        DocumentTools.SEARCH_DOCUMENTS: 0,
        DocumentTools.GET_DOCUMENT: 0
    }
}


def format_document_display(doc_data: Dict[str, Any], include_content: bool = False) -> str:
    """
    Format document data for display in Claude Code.
    
    Args:
        doc_data: Document data dictionary
        include_content: Whether to include full content
        
    Returns:
        Formatted display string
    """
    output = [
        f"📄 **{doc_data.get('title', 'Untitled')}**",
        f"🏷️ Category: {doc_data.get('category', 'Unknown')}",
    ]
    
    tags = doc_data.get('tags', [])
    if tags:
        output.append(f"🔖 Tags: {', '.join(tags)}")
    else:
        output.append("🔖 Tags: None")
    
    if doc_data.get('url'):
        output.append(f"🔗 URL: {doc_data.get('url')}")
    
    if doc_data.get('created'):
        try:
            # Parse and format the date
            created_dt = datetime.fromisoformat(doc_data['created'].replace('Z', '+00:00'))
            output.append(f"📅 Created: {created_dt.strftime('%Y-%m-%d %H:%M')}")
        except:
            output.append(f"📅 Created: {doc_data.get('created')}")
    
    if doc_data.get('notion_url'):
        output.append(f"🔗 Notion: {doc_data.get('notion_url')}")
    
    if doc_data.get('id'):
        output.append(f"🆔 ID: {doc_data.get('id')}")
    
    if include_content and doc_data.get('content'):
        content = doc_data['content']
        if len(content) > 500:
            content = content[:500] + "..."
        output.append(f"\n📝 **Content:**\n{content}")
    
    return "\n".join(output)


def format_search_results(search_response: Dict[str, Any]) -> str:
    """
    Format search results for display.
    
    Args:
        search_response: Search response data
        
    Returns:
        Formatted search results string
    """
    results = search_response.get('results', [])
    total_count = search_response.get('total_count', 0)
    query = search_response.get('query', '')
    
    if not results:
        return f"No documents found matching '{query}'"
    
    output = [f"Found {total_count} document(s) matching '{query}':\n"]
    
    for i, doc in enumerate(results, 1):
        output.append(f"**{i}. {doc.get('title', 'Untitled')}**")
        output.append(f"   Category: {doc.get('category', 'Unknown')}")
        
        tags = doc.get('tags', [])
        if tags:
            output.append(f"   Tags: {', '.join(tags)}")
        
        if doc.get('created'):
            try:
                created_dt = datetime.fromisoformat(doc['created'].replace('Z', '+00:00'))
                output.append(f"   Created: {created_dt.strftime('%Y-%m-%d %H:%M')}")
            except:
                pass
        
        if doc.get('id'):
            output.append(f"   ID: {doc.get('id')}")
        
        output.append("")  # Empty line between results
    
    # Add filters info if applied
    filters = search_response.get('filters_applied', {})
    filter_info = []
    if filters.get('tags'):
        filter_info.append(f"tags: {', '.join(filters['tags'])}")
    if filters.get('category'):
        filter_info.append(f"category: {filters['category']}")
    
    if filter_info:
        output.append(f"Filters applied: {', '.join(filter_info)}")
    
    return "\n".join(output)


async def serve_mcp():
    """Start the MCP server with comprehensive error handling."""
    logger.info("Starting Notion Document Store MCP Server")
    logger.info(f"Database ID: {NOTION_DATABASE_ID}")
    logger.info(f"API Version: {NOTION_API_VERSION}")
    
    # Initialize Notion client
    try:
        notion_client = NotionClient(
            api_secret=NOTION_API_SECRET,
            database_id=NOTION_DATABASE_ID,
            api_version=NOTION_API_VERSION
        )
        
        # Perform initial health check
        health_status = await notion_client.health_check()
        if health_status["status"] != "healthy":
            logger.error(f"Notion API health check failed: {health_status}")
            raise RuntimeError("Failed to connect to Notion API")
        
        logger.info("✅ Notion API connection verified")
        
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        raise
    
    # Initialize MCP server
    server = Server("notion-document-store")
    
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """List available MCP tools."""
        return [
            Tool(
                name=DocumentTools.ADD_DOCUMENT,
                description="Add a new document to your Notion knowledge base. Provide title, content, and optionally tags, category, URL, and notes.",
                inputSchema=AddDocumentRequest.model_json_schema(),
            ),
            Tool(
                name=DocumentTools.SEARCH_DOCUMENTS,
                description="Search for documents in your Notion knowledge base. You can search by title keywords and filter by tags or category.",
                inputSchema=SearchDocumentsRequest.model_json_schema(),
            ),
            Tool(
                name=DocumentTools.GET_DOCUMENT,
                description="Retrieve a specific document by its Notion page ID. Returns the full document content and metadata.",
                inputSchema=GetDocumentRequest.model_json_schema(),
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> List[TextContent]:
        """Handle MCP tool calls with comprehensive error handling and logging."""
        start_time = time.time()
        server_metrics["requests_total"] += 1
        
        logger.info(f"Tool called: {name} with arguments: {arguments}")
        
        try:
            if name not in [tool.value for tool in DocumentTools]:
                raise ValueError(f"Unknown tool: {name}")
            
            server_metrics["tools_called"][name] += 1
            
            # Route to appropriate handler
            if name == DocumentTools.ADD_DOCUMENT:
                result = await handle_add_document(notion_client, arguments)
            elif name == DocumentTools.SEARCH_DOCUMENTS:
                result = await handle_search_documents(notion_client, arguments)
            elif name == DocumentTools.GET_DOCUMENT:
                result = await handle_get_document(notion_client, arguments)
            else:
                raise ValueError(f"Unhandled tool: {name}")
            
            # Record success metrics
            server_metrics["requests_success"] += 1
            response_time = time.time() - start_time
            logger.info(f"Tool {name} completed successfully in {response_time:.2f}s")
            
            return [TextContent(type="text", text=result)]
            
        except NotionAPIError as e:
            # Handle Notion-specific errors
            server_metrics["requests_failed"] += 1
            error_msg = f"❌ Notion API Error: {e}"
            
            if e.status_code:
                error_msg += f" (Status: {e.status_code})"
            
            if e.details:
                error_msg += f"\nDetails: {e.details.get('message', 'No additional details')}"
            
            logger.error(f"Notion API error in {name}: {e}")
            return [TextContent(type="text", text=error_msg)]
            
        except ValueError as e:
            # Handle validation errors
            server_metrics["requests_failed"] += 1
            error_msg = f"❌ Validation Error: {str(e)}"
            logger.error(f"Validation error in {name}: {e}")
            return [TextContent(type="text", text=error_msg)]
            
        except Exception as e:
            # Handle unexpected errors
            server_metrics["requests_failed"] += 1
            error_msg = f"❌ Unexpected Error: {str(e)}"
            logger.error(f"Unexpected error in {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=error_msg)]


async def handle_add_document(notion_client: NotionClient, arguments: dict) -> str:
    """Handle add_document tool calls."""
    try:
        # Validate request
        req = AddDocumentRequest(**arguments)
        
        # Call Notion client
        result = await notion_client.add_document(
            title=req.title,
            content=req.content,
            tags=req.tags,
            url=req.url,
            category=req.category,
            notes=req.notes
        )
        
        # Format success response
        response = f"✅ Document added successfully!\n\n{format_document_display(result.dict())}"
        
        logger.info(f"Document created: {result.id} - {result.title}")
        return response
        
    except Exception as e:
        logger.error(f"Failed to add document: {e}")
        raise


async def handle_search_documents(notion_client: NotionClient, arguments: dict) -> str:
    """Handle search_documents tool calls."""
    try:
        # Validate request
        req = SearchDocumentsRequest(**arguments)
        
        # Call Notion client
        result = await notion_client.search_documents(
            query=req.query,
            tags=req.tags,
            category=req.category,
            limit=req.limit
        )
        
        # Format response
        response = format_search_results(result.dict())
        
        logger.info(f"Search completed: {result.total_count} results for '{req.query}'")
        return response
        
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        raise


async def handle_get_document(notion_client: NotionClient, arguments: dict) -> str:
    """Handle get_document tool calls."""
    try:
        # Validate request
        req = GetDocumentRequest(**arguments)
        
        # Call Notion client
        result = await notion_client.get_document(req.page_id)
        
        # Format response with full content
        response = f"📖 **Document Retrieved:**\n\n{format_document_display(result.dict(), include_content=True)}"
        
        logger.info(f"Document retrieved: {result.id} - {result.title}")
        return response
        
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise


def main():
    """CLI entry point for the MCP server."""
    import click
    
    @click.command()
    @click.option("-v", "--verbose", count=True, help="Verbose logging (-v for INFO, -vv for DEBUG)")
    @click.option("--log-file", default="notion_doc_store.log", help="Log file path")
    def cli(verbose: int, log_file: str):
        """Start the Notion Document Store MCP Server"""
        
        # Configure logging level
        if verbose >= 2:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger("httpx").setLevel(logging.DEBUG)
        elif verbose >= 1:
            logging.getLogger().setLevel(logging.INFO)
        else:
            logging.getLogger().setLevel(logging.WARNING)
        
        # Update log file handler
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                logging.getLogger().removeHandler(handler)
        
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logging.getLogger().addHandler(file_handler)
        
        logger.info("="*50)
        logger.info("Notion Document Store MCP Server Starting")
        logger.info(f"Log Level: {logging.getLogger().level}")
        logger.info(f"Log File: {log_file}")
        logger.info("="*50)
        
        try:
            asyncio.run(serve_mcp())
        except KeyboardInterrupt:
            logger.info("Server shutdown requested")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            raise
        finally:
            # Log final metrics
            uptime = time.time() - server_metrics["start_time"]
            logger.info("="*50)
            logger.info("Server Shutdown - Final Metrics:")
            logger.info(f"Uptime: {uptime:.2f} seconds")
            logger.info(f"Total Requests: {server_metrics['requests_total']}")
            logger.info(f"Successful: {server_metrics['requests_success']}")
            logger.info(f"Failed: {server_metrics['requests_failed']}")
            logger.info(f"Tools Called: {dict(server_metrics['tools_called'])}")
            logger.info("="*50)
    
    cli()


if __name__ == "__main__":
    main()