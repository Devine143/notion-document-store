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
from typing import List, Dict, Any, Optional
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
import click

from .modules.notion_client import NotionClient, NotionAPIError
from .modules.data_types import (
    AddDocumentRequest, 
    SearchDocumentsRequest, 
    GetDocumentRequest,
    DocumentCategory,
    ErrorResponse,
    SuccessResponse
)
from .health_server import start_health_server

# Configure logging
handlers = [logging.StreamHandler()]

# Add file handler only if not in Docker (detected by environment)
if not os.getenv('DOCKER_CONTAINER'):
    try:
        handlers.append(logging.FileHandler('/app/logs/notion_doc_store.log', mode='a'))
    except (PermissionError, OSError):
        # Fall back to just console logging if file logging fails
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
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


# Initialize FastMCP server
mcp = FastMCP("notion-document-store")


# Global variables
notion_client: Optional[NotionClient] = None
health_runner = None

# Global metrics tracking
server_metrics = {
    "start_time": time.time(),
    "requests_total": 0,
    "requests_success": 0,
    "requests_failed": 0,
    "tools_called": {
        "add_document": 0,
        "search_documents": 0,
        "get_document": 0
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


async def initialize_server():
    """Initialize Notion client and health server."""
    global notion_client, health_runner
    
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
    
    # Start health check server in background
    try:
        health_runner = await start_health_server(notion_client, server_metrics)
    except Exception as e:
        logger.warning(f"Failed to start health check server: {e}")
        logger.warning("Continuing without health check endpoints...")


# FastMCP Tool Decorators
@mcp.tool()
async def add_document(
    title: str,
    content: str,
    tags: Optional[List[str]] = None,
    url: Optional[str] = None,
    category: Optional[DocumentCategory] = None,
    notes: Optional[str] = None
) -> str:
    """Add a new document to your Notion knowledge base. Provide title, content, and optionally tags, category, URL, and notes."""
    if not notion_client:
        await initialize_server()
    
    start_time = time.time()
    server_metrics["requests_total"] += 1
    server_metrics["tools_called"]["add_document"] += 1
    
    logger.info(f"Adding document: {title}")
    
    try:
        # Call Notion client
        result = await notion_client.add_document(
            title=title,
            content=content,
            tags=tags or [],
            url=url,
            category=category,
            notes=notes
        )
        
        # Format success response
        response = f"✅ Document added successfully!\n\n{format_document_display(result.dict())}"
        
        # Record success metrics
        server_metrics["requests_success"] += 1
        response_time = time.time() - start_time
        logger.info(f"Document created: {result.id} - {result.title} in {response_time:.2f}s")
        
        return response
        
    except Exception as e:
        server_metrics["requests_failed"] += 1
        logger.error(f"Failed to add document: {e}")
        return f"❌ Error adding document: {str(e)}"


@mcp.tool()
async def search_documents(
    query: str,
    tags: Optional[List[str]] = None,
    category: Optional[DocumentCategory] = None,
    limit: Optional[int] = 10
) -> str:
    """Search for documents in your Notion knowledge base. You can search by title keywords and filter by tags or category."""
    if not notion_client:
        await initialize_server()
    
    start_time = time.time()
    server_metrics["requests_total"] += 1
    server_metrics["tools_called"]["search_documents"] += 1
    
    logger.info(f"Searching documents: {query}")
    
    try:
        # Call Notion client
        result = await notion_client.search_documents(
            query=query,
            tags=tags,
            category=category,
            limit=limit or 10
        )
        
        # Format response
        response = format_search_results(result.dict())
        
        # Record success metrics
        server_metrics["requests_success"] += 1
        response_time = time.time() - start_time
        logger.info(f"Search completed: {result.total_count} results for '{query}' in {response_time:.2f}s")
        
        return response
        
    except Exception as e:
        server_metrics["requests_failed"] += 1
        logger.error(f"Failed to search documents: {e}")
        return f"❌ Error searching documents: {str(e)}"


@mcp.tool()
async def get_document(page_id: str) -> str:
    """Retrieve a specific document by its Notion page ID. Returns the full document content and metadata."""
    if not notion_client:
        await initialize_server()
    
    start_time = time.time()
    server_metrics["requests_total"] += 1
    server_metrics["tools_called"]["get_document"] += 1
    
    logger.info(f"Getting document: {page_id}")
    
    try:
        # Call Notion client
        result = await notion_client.get_document(page_id)
        
        # Format response with full content
        response = f"📖 **Document Retrieved:**\n\n{format_document_display(result.dict(), include_content=True)}"
        
        # Record success metrics
        server_metrics["requests_success"] += 1
        response_time = time.time() - start_time
        logger.info(f"Document retrieved: {result.id} - {result.title} in {response_time:.2f}s")
        
        return response
        
    except Exception as e:
        server_metrics["requests_failed"] += 1
        logger.error(f"Failed to get document: {e}")
        return f"❌ Error retrieving document: {str(e)}"


async def serve_mcp(transport: str = "stdio"):
    """Start MCP server with specified transport."""
    global health_runner
    
    # Initialize server components
    await initialize_server()
    
    logger.info(f"🚀 Starting MCP server with {transport} transport")
    
    try:
        # Use FastMCP's built-in transport handling
        if transport == "sse":
            await mcp.run_sse_async()
        else:
            await mcp.run_stdio_async()
    except Exception as e:
        logger.error(f"MCP server error: {e}")
        raise
    finally:
        # Cleanup health server
        if health_runner:
            try:
                await health_runner.cleanup()
                logger.info("Health check server stopped")
            except Exception as e:
                logger.warning(f"Error stopping health server: {e}")


# Helper function to serve with port binding for SSE
async def serve_sse_with_port(host: str = "0.0.0.0", port: int = 3000):
    """Start FastMCP SSE server with custom host/port."""
    # Initialize server
    await initialize_server()
    
    logger.info(f"🚀 Starting FastMCP SSE server on {host}:{port}")
    
    # Set environment variables for FastMCP SSE server
    os.environ["MCP_SSE_HOST"] = host
    os.environ["MCP_SSE_PORT"] = str(port)
    
    try:
        await mcp.run_sse_async()
    except Exception as e:
        logger.error(f"SSE server error: {e}")
        raise
    finally:
        if health_runner:
            try:
                await health_runner.cleanup()
                logger.info("Health check server stopped")
            except Exception as e:
                logger.warning(f"Error stopping health server: {e}")


def main():
    """CLI entry point for the MCP server."""
    
    @click.command()
    @click.option("-v", "--verbose", count=True, help="Verbose logging (-v for INFO, -vv for DEBUG)")
    @click.option("--log-file", default="/app/logs/notion_doc_store.log", help="Log file path")
    @click.option("--transport", type=click.Choice(['stdio', 'sse']), default='stdio', 
                  help="Transport type: stdio for local, sse for Docker/HTTP")
    @click.option("--host", default="0.0.0.0", help="Host for SSE transport")
    @click.option("--port", default=3000, type=int, help="Port for SSE transport")
    def cli(verbose: int, log_file: str, transport: str, host: str, port: int):
        """Start the Notion Document Store MCP Server"""
        
        # Configure logging level
        if verbose >= 2:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger("httpx").setLevel(logging.DEBUG)
        elif verbose >= 1:
            logging.getLogger().setLevel(logging.INFO)
        else:
            logging.getLogger().setLevel(logging.WARNING)
        
        # Update log file handler (only if not in Docker)
        if not os.getenv('DOCKER_CONTAINER'):
            for handler in logging.getLogger().handlers:
                if isinstance(handler, logging.FileHandler):
                    handler.close()
                    logging.getLogger().removeHandler(handler)
            
            try:
                file_handler = logging.FileHandler(log_file, mode='a')
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
                logging.getLogger().addHandler(file_handler)
            except (PermissionError, OSError):
                logger.warning(f"Could not create log file {log_file}, using console only")
        
        logger.info("="*50)
        logger.info("Notion Document Store MCP Server Starting")
        logger.info(f"Log Level: {logging.getLogger().level}")
        logger.info(f"Log File: {log_file}")
        logger.info(f"Transport: {transport}")
        if transport == 'sse':
            logger.info(f"SSE Host: {host}:{port}")
        logger.info("="*50)
        
        try:
            if transport == 'sse':
                asyncio.run(serve_sse_with_port(host, port))
            else:
                asyncio.run(serve_mcp(transport))
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