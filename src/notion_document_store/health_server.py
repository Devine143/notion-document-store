"""
HTTP health check server for Docker monitoring.

This module provides a simple HTTP server that runs alongside the MCP server
to provide health check endpoints for Docker and monitoring systems.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any
from aiohttp import web, web_request
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """HTTP server for health checks and monitoring."""
    
    def __init__(self, notion_client, server_metrics: Dict[str, Any]):
        self.notion_client = notion_client
        self.server_metrics = server_metrics
        self.start_time = time.time()
        self.app = web.Application()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup HTTP routes for health checks."""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/metrics', self.get_metrics)
        self.app.router.add_get('/status', self.get_status)
    
    async def health_check(self, request: web_request.Request) -> web.Response:
        """
        Primary health check endpoint.
        
        Returns HTTP 200 if healthy, 503 if unhealthy.
        """
        try:
            # Quick health check of Notion client
            health_status = await self.notion_client.health_check()
            
            if health_status["status"] == "healthy":
                response_data = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "uptime_seconds": time.time() - self.start_time,
                    "database_accessible": health_status.get("database_accessible", False),
                    "response_time": health_status.get("response_time", 0),
                }
                return web.json_response(response_data, status=200)
            else:
                response_data = {
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "error": health_status.get("error", "Unknown error"),
                    "database_accessible": False,
                }
                return web.json_response(response_data, status=503)
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            response_data = {
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "database_accessible": False,
            }
            return web.json_response(response_data, status=503)
    
    async def get_metrics(self, request: web_request.Request) -> web.Response:
        """
        Detailed metrics endpoint for monitoring.
        """
        try:
            uptime = time.time() - self.start_time
            notion_metrics = self.notion_client.get_metrics()
            
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": uptime,
                "server_metrics": self.server_metrics.copy(),
                "notion_client_metrics": notion_metrics,
                "memory_info": {
                    "available": "not_implemented",  # Could add psutil for detailed memory info
                },
                "performance": {
                    "average_response_time": notion_metrics.get("average_response_time", 0),
                    "success_rate": self._calculate_success_rate(),
                }
            }
            
            return web.json_response(metrics, status=200)
            
        except Exception as e:
            logger.error(f"Metrics endpoint failed: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def get_status(self, request: web_request.Request) -> web.Response:
        """
        Comprehensive status endpoint.
        """
        try:
            health_status = await self.notion_client.health_check()
            uptime = time.time() - self.start_time
            
            status = {
                "service": "notion-document-store",
                "version": "0.1.0",
                "status": health_status["status"],
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": uptime,
                "uptime_human": self._format_uptime(uptime),
                "notion_api": {
                    "accessible": health_status.get("database_accessible", False),
                    "response_time": health_status.get("response_time", 0),
                },
                "mcp_server": {
                    "requests_total": self.server_metrics.get("requests_total", 0),
                    "requests_success": self.server_metrics.get("requests_success", 0),
                    "requests_failed": self.server_metrics.get("requests_failed", 0),
                    "tools_called": self.server_metrics.get("tools_called", {}),
                }
            }
            
            return web.json_response(status, status=200)
            
        except Exception as e:
            logger.error(f"Status endpoint failed: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    def _calculate_success_rate(self) -> float:
        """Calculate request success rate."""
        total = self.server_metrics.get("requests_total", 0)
        success = self.server_metrics.get("requests_success", 0)
        
        if total == 0:
            return 100.0
        
        return (success / total) * 100.0
    
    def _format_uptime(self, uptime_seconds: float) -> str:
        """Format uptime in human-readable format."""
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    async def start(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the health check server."""
        logger.info(f"Starting health check server on {host}:{port}")
        
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, host, port)
            await site.start()
            
            logger.info(f"✅ Health check server running on http://{host}:{port}")
            logger.info(f"   - Health: http://{host}:{port}/health")
            logger.info(f"   - Metrics: http://{host}:{port}/metrics")
            logger.info(f"   - Status: http://{host}:{port}/status")
            
            return runner
            
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
            raise


async def start_health_server(notion_client, server_metrics: Dict[str, Any]) -> web.AppRunner:
    """
    Convenience function to start the health check server.
    
    Args:
        notion_client: The Notion API client instance
        server_metrics: Server metrics dictionary
        
    Returns:
        AppRunner instance for cleanup
    """
    health_server = HealthCheckServer(notion_client, server_metrics)
    return await health_server.start()