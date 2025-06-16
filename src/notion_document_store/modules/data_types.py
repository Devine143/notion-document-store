"""
Data types and Pydantic models for the Notion Document Store MCP server.

This module defines all request and response models for MCP tool operations,
providing type safety and validation for document management operations.
"""
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class DocumentCategory(str, Enum):
    """Supported document categories matching Notion database options."""
    GENERAL = "General"
    CODE = "Code"
    TUTORIAL = "Tutorial"
    REFERENCE = "Reference"
    METHODOLOGY = "Methodology"


class AddDocumentRequest(BaseModel):
    """Request model for adding a new document to Notion."""
    title: str = Field(..., description="Document title", min_length=1, max_length=200)
    content: str = Field(..., description="Document content/body text", min_length=1)
    tags: List[str] = Field(default_factory=list, description="Document tags for categorization")
    url: Optional[str] = Field(None, description="Optional URL reference")
    category: DocumentCategory = Field(
        default=DocumentCategory.GENERAL, 
        description="Document category"
    )
    notes: Optional[str] = Field(None, description="Additional notes or comments")

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            DocumentCategory: lambda v: v.value
        }


class SearchDocumentsRequest(BaseModel):
    """Request model for searching documents in Notion."""
    query: str = Field(..., description="Search query for document titles", min_length=1)
    tags: List[str] = Field(default_factory=list, description="Filter by specific tags")
    category: Optional[DocumentCategory] = Field(None, description="Filter by category")
    limit: int = Field(default=10, description="Maximum number of results", ge=1, le=100)

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            DocumentCategory: lambda v: v.value if v else None
        }


class GetDocumentRequest(BaseModel):
    """Request model for retrieving a specific document by ID."""
    page_id: str = Field(..., description="Notion page ID", min_length=1)


class DocumentResponse(BaseModel):
    """Response model for document data."""
    id: str = Field(..., description="Notion page ID")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document content")
    tags: List[str] = Field(default_factory=list, description="Document tags")
    category: str = Field(..., description="Document category")
    url: Optional[str] = Field(None, description="Document URL if provided")
    created: str = Field(..., description="Creation timestamp")
    notion_url: str = Field(..., description="Direct Notion page URL")


class DocumentSummary(BaseModel):
    """Lightweight document summary for search results."""
    id: str = Field(..., description="Notion page ID")
    title: str = Field(..., description="Document title")
    category: str = Field(..., description="Document category")
    tags: List[str] = Field(default_factory=list, description="Document tags")
    created: str = Field(..., description="Creation timestamp")
    notion_url: str = Field(..., description="Direct Notion page URL")


class SearchDocumentsResponse(BaseModel):
    """Response model for search operations."""
    results: List[DocumentSummary] = Field(default_factory=list, description="Search results")
    total_count: int = Field(..., description="Total number of matching documents")
    query: str = Field(..., description="Original search query")
    filters_applied: dict = Field(default_factory=dict, description="Applied search filters")


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")


class SuccessResponse(BaseModel):
    """Standard success response model."""
    success: bool = Field(True, description="Operation success indicator")
    message: str = Field(..., description="Success message")
    data: Optional[dict] = Field(None, description="Additional response data")


# Type aliases for common types
NotionPageId = str
NotionUrl = str
DocumentTags = List[str]


# Validation helpers
def validate_notion_page_id(page_id: str) -> bool:
    """
    Validate that a string looks like a valid Notion page ID.
    
    Args:
        page_id: The page ID to validate
        
    Returns:
        True if the ID appears valid, False otherwise
    """
    if not page_id:
        return False
    
    # Remove dashes for length check
    clean_id = page_id.replace('-', '')
    
    # Should be 32 hex characters
    if len(clean_id) != 32:
        return False
    
    # Should be valid hexadecimal
    try:
        int(clean_id, 16)
        return True
    except ValueError:
        return False


def format_notion_url(page_id: str) -> str:
    """
    Format a Notion page ID into a direct URL.
    
    Args:
        page_id: The Notion page ID
        
    Returns:
        Direct Notion page URL
    """
    # Remove dashes and format with dashes in standard positions
    clean_id = page_id.replace('-', '')
    formatted_id = f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"
    return f"https://www.notion.so/{formatted_id}"


def sanitize_tags(tags: List[str]) -> List[str]:
    """
    Sanitize and normalize document tags.
    
    Args:
        tags: List of raw tag strings
        
    Returns:
        List of normalized tags
    """
    if not tags:
        return []
    
    sanitized = []
    for tag in tags:
        if isinstance(tag, str) and tag.strip():
            # Normalize: lowercase, strip whitespace, limit length
            normalized = tag.strip().lower()[:50]
            if normalized and normalized not in sanitized:
                sanitized.append(normalized)
    
    return sanitized[:10]  # Limit to 10 tags maximum


def extract_title_from_content(content: str, max_length: int = 100) -> str:
    """
    Extract a title from content if no title is provided.
    
    Args:
        content: The document content
        max_length: Maximum title length
        
    Returns:
        Extracted title string
    """
    if not content:
        return "Untitled Document"
    
    # Take first line or first sentence
    first_line = content.split('\n')[0].strip()
    if first_line:
        # Truncate if too long
        if len(first_line) > max_length:
            return first_line[:max_length-3] + "..."
        return first_line
    
    return "Untitled Document"