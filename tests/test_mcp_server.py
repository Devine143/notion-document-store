#!/usr/bin/env python3
"""
Simple test script for the MCP server components.
Tests the Notion client and basic functionality.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from notion_document_store.modules.notion_client import NotionClient
from notion_document_store.modules.data_types import DocumentCategory

async def test_notion_client():
    """Test the Notion client directly."""
    print("🧪 Testing Notion Client")
    
    # Get environment variables
    api_secret = os.getenv("NOTION_INTERNAL_INTEGRATION_SECRET")
    database_id = os.getenv("NOTION_DATABASE_ID")
    
    if not api_secret or not database_id:
        print("❌ Environment variables not set")
        return False
    
    try:
        # Initialize client
        client = NotionClient(api_secret, database_id)
        print(f"✅ Client initialized")
        
        # Test health check
        print("🔍 Testing health check...")
        health = await client.health_check()
        print(f"Health status: {health}")
        
        if health["status"] == "healthy":
            print("✅ Health check passed")
            
            # Test add document
            print("📝 Testing document creation...")
            doc = await client.add_document(
                title="MCP Test Document",
                content="This is a test document created by the MCP server test script.",
                tags=["test", "mcp", "validation"],
                category=DocumentCategory.GENERAL
            )
            print(f"✅ Document created: {doc.id}")
            
            # Test search
            print("🔍 Testing document search...")
            search_result = await client.search_documents("MCP Test", limit=5)
            print(f"✅ Search completed: {search_result.total_count} results")
            
            # Test get document
            if search_result.results:
                doc_id = search_result.results[0].id
                print(f"📖 Testing document retrieval for {doc_id}...")
                retrieved_doc = await client.get_document(doc_id)
                print(f"✅ Document retrieved: {retrieved_doc.title}")
            
            return True
        else:
            print(f"❌ Health check failed: {health}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    print("🎯 MCP Server Component Tests")
    print("=" * 40)
    
    # Load environment
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    success = await test_notion_client()
    
    print("=" * 40)
    if success:
        print("🎉 All tests passed!")
    else:
        print("🚨 Some tests failed!")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)