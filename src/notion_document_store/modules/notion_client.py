"""
Robust Notion API client with retry logic, error handling, and rate limiting.

This module provides a comprehensive interface to the Notion API for document
management operations, including automatic retry logic, exponential backoff,
and graceful error handling.
"""
import httpx
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import json
import time
from enum import Enum

from .data_types import (
    DocumentCategory, 
    DocumentResponse, 
    DocumentSummary,
    SearchDocumentsResponse,
    validate_notion_page_id,
    format_notion_url,
    sanitize_tags,
    extract_title_from_content
)

# Configure logging
logger = logging.getLogger(__name__)


class NotionAPIError(Exception):
    """Custom exception for Notion API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class RetryStrategy(Enum):
    """Retry strategies for different types of errors."""
    NO_RETRY = "no_retry"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    RATE_LIMIT_BACKOFF = "rate_limit_backoff"


class NotionClient:
    """
    Robust Notion API client with comprehensive error handling.
    
    Features:
    - Automatic retry logic with exponential backoff
    - Rate limiting handling with proper delays
    - Network error recovery
    - Structured error reporting
    - Request/response logging
    """
    
    def __init__(self, api_secret: str, database_id: str, api_version: str = "2022-06-28"):
        """
        Initialize the Notion client.
        
        Args:
            api_secret: Notion integration secret
            database_id: Target database ID
            api_version: Notion API version
        """
        self.api_secret = api_secret
        self.database_id = database_id
        self.api_version = api_version
        self.base_url = "https://api.notion.com/v1"
        self.timeout = httpx.Timeout(30.0)
        
        # Rate limiting tracking
        self._last_request_time = 0.0
        self._request_count = 0
        self._min_delay_between_requests = 0.1  # Minimum delay between requests
        
        # Performance metrics
        self.metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "average_response_time": 0.0,
            "retry_count": 0
        }
        
    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for Notion API requests."""
        return {
            "Authorization": f"Bearer {self.api_secret}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json",
            "User-Agent": f"NotionDocumentStore/0.1.0"
        }
    
    async def _rate_limit_delay(self):
        """Implement basic rate limiting."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        
        if elapsed < self._min_delay_between_requests:
            await asyncio.sleep(self._min_delay_between_requests - elapsed)
        
        self._last_request_time = time.time()
    
    def _determine_retry_strategy(self, status_code: int, error_type: str) -> RetryStrategy:
        """
        Determine the appropriate retry strategy based on error type.
        
        Args:
            status_code: HTTP status code
            error_type: Type of error encountered
            
        Returns:
            Appropriate retry strategy
        """
        if status_code == 429:  # Rate limited
            return RetryStrategy.RATE_LIMIT_BACKOFF
        elif status_code >= 500:  # Server errors
            return RetryStrategy.EXPONENTIAL_BACKOFF
        elif status_code in [401, 403, 404]:  # Client errors (don't retry)
            return RetryStrategy.NO_RETRY
        elif "timeout" in error_type.lower() or "network" in error_type.lower():
            return RetryStrategy.EXPONENTIAL_BACKOFF
        else:
            return RetryStrategy.NO_RETRY
    
    async def _make_request(
        self, 
        method: str, 
        url: str, 
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with comprehensive retry logic and error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            max_retries: Maximum retry attempts
            **kwargs: Additional request parameters
            
        Returns:
            Response data as dictionary
            
        Raises:
            NotionAPIError: For API-related errors
        """
        await self._rate_limit_delay()
        
        retry_count = 0
        last_error = None
        start_time = time.time()
        
        self.metrics["requests_total"] += 1
        
        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"Making request: {method} {url} (attempt {attempt + 1})")
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=self._get_headers(),
                        **kwargs
                    )
                    
                    # Log response details
                    response_time = time.time() - start_time
                    logger.debug(f"Response: {response.status_code} in {response_time:.2f}s")
                    
                    # Success case
                    if response.status_code == 200:
                        self.metrics["requests_success"] += 1
                        self._update_response_time_metric(response_time)
                        return response.json()
                    
                    # Handle different error scenarios
                    error_data = None
                    try:
                        error_data = response.json()
                    except:
                        error_data = {"message": response.text}
                    
                    retry_strategy = self._determine_retry_strategy(
                        response.status_code, 
                        error_data.get("code", "unknown")
                    )
                    
                    if retry_strategy == RetryStrategy.NO_RETRY:
                        # Don't retry client errors
                        self.metrics["requests_failed"] += 1
                        raise NotionAPIError(
                            f"Notion API error: {error_data.get('message', 'Unknown error')}",
                            status_code=response.status_code,
                            details=error_data
                        )
                    
                    elif retry_strategy == RetryStrategy.RATE_LIMIT_BACKOFF:
                        if attempt < max_retries:
                            # Use Retry-After header if available, otherwise exponential backoff
                            retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                            logger.warning(f"Rate limited, waiting {retry_after}s before retry")
                            await asyncio.sleep(retry_after)
                            retry_count += 1
                            continue
                    
                    elif retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
                        if attempt < max_retries:
                            backoff_time = min(2 ** attempt, 60)  # Cap at 60 seconds
                            logger.warning(f"Server error {response.status_code}, retrying in {backoff_time}s")
                            await asyncio.sleep(backoff_time)
                            retry_count += 1
                            continue
                    
                    # Final attempt failed
                    last_error = NotionAPIError(
                        f"Notion API error after {max_retries} retries: {error_data.get('message', 'Unknown error')}",
                        status_code=response.status_code,
                        details=error_data
                    )
                    
            except httpx.TimeoutException as e:
                logger.warning(f"Request timeout (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    backoff_time = min(2 ** attempt, 30)
                    await asyncio.sleep(backoff_time)
                    retry_count += 1
                    continue
                last_error = NotionAPIError(f"Request timeout after {max_retries} retries")
                
            except httpx.NetworkError as e:
                logger.warning(f"Network error (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    backoff_time = min(2 ** attempt, 30)
                    await asyncio.sleep(backoff_time)
                    retry_count += 1
                    continue
                last_error = NotionAPIError(f"Network error after {max_retries} retries: {e}")
        
        # All retries exhausted
        self.metrics["requests_failed"] += 1
        self.metrics["retry_count"] += retry_count
        
        if last_error:
            raise last_error
        else:
            raise NotionAPIError("Max retries exceeded with unknown error")
    
    def _update_response_time_metric(self, response_time: float):
        """Update average response time metric."""
        current_avg = self.metrics["average_response_time"]
        current_count = self.metrics["requests_success"]
        
        if current_count == 1:
            self.metrics["average_response_time"] = response_time
        else:
            # Calculate running average
            self.metrics["average_response_time"] = (
                (current_avg * (current_count - 1) + response_time) / current_count
            )
    
    async def add_document(
        self, 
        title: str, 
        content: str, 
        tags: List[str] = None, 
        url: Optional[str] = None, 
        category: Union[str, DocumentCategory] = DocumentCategory.GENERAL, 
        notes: Optional[str] = None
    ) -> DocumentResponse:
        """
        Add a new document to the Notion database.
        
        Args:
            title: Document title
            content: Document content
            tags: List of tags
            url: Optional URL reference
            category: Document category
            notes: Optional additional notes
            
        Returns:
            DocumentResponse with created document details
            
        Raises:
            NotionAPIError: If document creation fails
        """
        logger.info(f"Creating document: {title}")
        
        # Validate and sanitize inputs
        if not title or not title.strip():
            title = extract_title_from_content(content)
        
        tags = sanitize_tags(tags or [])
        
        if isinstance(category, DocumentCategory):
            category_name = category.value
        else:
            category_name = str(category)
        
        # Build page properties
        properties = {
            "Title": {"title": [{"text": {"content": title[:200]}}]},  # Notion title limit
            "Category": {"select": {"name": category_name}},
            "Tags": {"multi_select": [{"name": tag} for tag in tags]},
            "Created": {"date": {"start": datetime.now().isoformat()}}
        }
        
        if url:
            properties["URL"] = {"url": url}
        
        # Build page content
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]  # Notion block limit
                }
            }
        ]
        
        # Add notes section if provided
        if notes:
            children.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Notes"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": notes[:2000]}}]
                    }
                }
            ])
        
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "children": children
        }
        
        try:
            result = await self._make_request("POST", f"{self.base_url}/pages", json=payload)
            
            page_id = result["id"]
            created_time = result.get("created_time", datetime.now().isoformat())
            
            return DocumentResponse(
                id=page_id,
                title=title,
                content=content,
                tags=tags,
                category=category_name,
                url=url,
                created=created_time,
                notion_url=format_notion_url(page_id)
            )
            
        except Exception as e:
            logger.error(f"Failed to create document '{title}': {e}")
            raise
    
    async def search_documents(
        self, 
        query: str, 
        tags: List[str] = None, 
        category: Optional[Union[str, DocumentCategory]] = None, 
        limit: int = 10
    ) -> SearchDocumentsResponse:
        """
        Search documents in the Notion database.
        
        Args:
            query: Search query for document titles
            tags: Filter by specific tags
            category: Filter by category
            limit: Maximum number of results
            
        Returns:
            SearchDocumentsResponse with search results
            
        Raises:
            NotionAPIError: If search fails
        """
        logger.info(f"Searching documents: query='{query}', tags={tags}, category={category}")
        
        # Build filter conditions
        filter_conditions = []
        
        if query:
            filter_conditions.append({
                "property": "Title",
                "title": {"contains": query}
            })
        
        if tags:
            for tag in tags:
                filter_conditions.append({
                    "property": "Tags",
                    "multi_select": {"contains": tag}
                })
        
        if category:
            if isinstance(category, DocumentCategory):
                category_name = category.value
            else:
                category_name = str(category)
            
            filter_conditions.append({
                "property": "Category",
                "select": {"equals": category_name}
            })
        
        # Build query payload
        payload = {
            "page_size": min(limit, 100),  # Notion API limit
            "sorts": [
                {
                    "property": "Created",
                    "direction": "descending"
                }
            ]
        }
        
        if filter_conditions:
            if len(filter_conditions) == 1:
                payload["filter"] = filter_conditions[0]
            else:
                payload["filter"] = {"and": filter_conditions}
        
        try:
            result = await self._make_request(
                "POST", 
                f"{self.base_url}/databases/{self.database_id}/query", 
                json=payload
            )
            
            documents = []
            for page in result.get("results", []):
                try:
                    doc_summary = self._parse_page_summary(page)
                    documents.append(doc_summary)
                except Exception as e:
                    logger.warning(f"Failed to parse page {page.get('id', 'unknown')}: {e}")
                    continue
            
            return SearchDocumentsResponse(
                results=documents,
                total_count=len(documents),
                query=query,
                filters_applied={
                    "tags": tags or [],
                    "category": category.value if isinstance(category, DocumentCategory) else category
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            raise
    
    async def get_document(self, page_id: str) -> DocumentResponse:
        """
        Get a specific document by its Notion page ID.
        
        Args:
            page_id: Notion page ID
            
        Returns:
            DocumentResponse with full document details
            
        Raises:
            NotionAPIError: If document retrieval fails
        """
        logger.info(f"Retrieving document: {page_id}")
        
        if not validate_notion_page_id(page_id):
            raise NotionAPIError(f"Invalid Notion page ID: {page_id}")
        
        try:
            # Get page properties
            page_data = await self._make_request("GET", f"{self.base_url}/pages/{page_id}")
            
            # Get page content blocks
            blocks_data = await self._make_request("GET", f"{self.base_url}/blocks/{page_id}/children")
            
            # Parse the response
            return self._parse_full_document(page_data, blocks_data.get("results", []))
            
        except Exception as e:
            logger.error(f"Failed to retrieve document {page_id}: {e}")
            raise
    
    def _parse_page_summary(self, page_data: dict) -> DocumentSummary:
        """Parse a Notion page into a DocumentSummary."""
        properties = page_data.get("properties", {})
        
        # Extract title
        title = "Untitled"
        if properties.get("Title", {}).get("title"):
            title = "".join([
                text.get("plain_text", "") 
                for text in properties["Title"]["title"]
            ]) or "Untitled"
        
        # Extract category
        category = "General"
        if properties.get("Category", {}).get("select"):
            category = properties["Category"]["select"]["name"]
        
        # Extract tags
        tags = []
        if properties.get("Tags", {}).get("multi_select"):
            tags = [tag["name"] for tag in properties["Tags"]["multi_select"]]
        
        # Extract created time
        created = page_data.get("created_time", datetime.now().isoformat())
        
        page_id = page_data.get("id", "")
        
        return DocumentSummary(
            id=page_id,
            title=title,
            category=category,
            tags=tags,
            created=created,
            notion_url=format_notion_url(page_id)
        )
    
    def _parse_full_document(self, page_data: dict, blocks: List[dict]) -> DocumentResponse:
        """Parse a Notion page and its blocks into a full DocumentResponse."""
        properties = page_data.get("properties", {})
        
        # Extract title
        title = "Untitled"
        if properties.get("Title", {}).get("title"):
            title = "".join([
                text.get("plain_text", "") 
                for text in properties["Title"]["title"]
            ]) or "Untitled"
        
        # Extract category
        category = "General"
        if properties.get("Category", {}).get("select"):
            category = properties["Category"]["select"]["name"]
        
        # Extract tags
        tags = []
        if properties.get("Tags", {}).get("multi_select"):
            tags = [tag["name"] for tag in properties["Tags"]["multi_select"]]
        
        # Extract URL
        url = None
        if properties.get("URL", {}).get("url"):
            url = properties["URL"]["url"]
        
        # Extract created time
        created = page_data.get("created_time", datetime.now().isoformat())
        
        # Extract content from blocks
        content_parts = []
        for block in blocks:
            block_text = self._extract_block_text(block)
            if block_text:
                content_parts.append(block_text)
        
        content = "\n\n".join(content_parts) if content_parts else "No content available"
        
        page_id = page_data.get("id", "")
        
        return DocumentResponse(
            id=page_id,
            title=title,
            content=content,
            tags=tags,
            category=category,
            url=url,
            created=created,
            notion_url=format_notion_url(page_id)
        )
    
    def _extract_block_text(self, block: dict) -> Optional[str]:
        """Extract text content from a Notion block."""
        block_type = block.get("type")
        
        if not block_type:
            return None
        
        # Handle different block types
        text_content = ""
        
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            text_content = "".join([text.get("plain_text", "") for text in rich_text])
        elif block_type == "bulleted_list_item":
            rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
            text_content = "• " + "".join([text.get("plain_text", "") for text in rich_text])
        elif block_type == "numbered_list_item":
            rich_text = block.get("numbered_list_item", {}).get("rich_text", [])
            text_content = "1. " + "".join([text.get("plain_text", "") for text in rich_text])
        elif block_type == "code":
            rich_text = block.get("code", {}).get("rich_text", [])
            language = block.get("code", {}).get("language", "")
            code_text = "".join([text.get("plain_text", "") for text in rich_text])
            text_content = f"```{language}\n{code_text}\n```"
        
        return text_content.strip() if text_content.strip() else None
    
    def get_metrics(self) -> dict:
        """Get performance metrics for the client."""
        return self.metrics.copy()
    
    async def health_check(self) -> dict:
        """
        Perform a health check on the Notion API connection.
        
        Returns:
            Health status dictionary
        """
        try:
            import time as time_module  # Use explicit import to avoid conflicts
            start_time = time_module.time()
            
            # Simple direct request without rate limiting for health check
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/databases/{self.database_id}",
                    headers=self._get_headers()
                )
                
                response_time = time_module.time() - start_time
                
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time": response_time,
                        "database_accessible": True,
                        "metrics": self.get_metrics()
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"API returned status {response.status_code}",
                        "database_accessible": False,
                        "metrics": self.get_metrics()
                    }
                    
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "database_accessible": False,
                "metrics": self.get_metrics()
            }