#!/usr/bin/env python3
"""
Notion API Test Script for Document Store MCP
Tests all CRUD operations and error scenarios
"""
import httpx
import json
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

# Configuration - Replace with your actual values
NOTION_SECRET = os.getenv("NOTION_INTERNAL_INTEGRATION_SECRET", "YOUR_SECRET_HERE")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "YOUR_DATABASE_ID")
NOTION_API_VERSION = "2022-06-28"

class NotionAPITester:
    def __init__(self, secret: str, database_id: str):
        self.secret = secret
        self.database_id = database_id
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {secret}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json"
        }
        self.test_page_id: Optional[str] = None
        
    async def test_database_access(self) -> bool:
        """Test database access permissions"""
        print("🔍 Testing database access...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/databases/{self.database_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    db_data = response.json()
                    title_data = db_data.get('title', [])
                    if title_data and len(title_data) > 0:
                        title = title_data[0].get('plain_text', 'Untitled')
                    else:
                        title = 'Untitled Database'
                    print(f"✅ Database access successful: {title}")
                    
                    # Validate required properties
                    properties = db_data.get("properties", {})
                    required_props = ["Title", "Category", "Tags", "URL", "Created"]
                    missing_props = [prop for prop in required_props if prop not in properties]
                    
                    if missing_props:
                        print(f"⚠️ Missing required properties: {missing_props}")
                        return False
                    else:
                        print("✅ All required properties found")
                        return True
                        
                else:
                    print(f"❌ Database access failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return False
                    
            except Exception as e:
                print(f"❌ Database access error: {e}")
                return False
    
    async def test_create_document(self) -> Optional[str]:
        """Test document creation"""
        print("📝 Testing document creation...")
        
        create_payload = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Title": {"title": [{"text": {"content": "Test Document - API Validation"}}]},
                "Category": {"select": {"name": "General"}},
                "Tags": {"multi_select": [{"name": "test"}, {"name": "api-validation"}]},
                "URL": {"url": "https://github.com/Devine143/notion-document-store"},
                "Created": {"date": {"start": datetime.now().isoformat()}}
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": "This is a test document created by the Notion API test script to validate CRUD operations for the Document Store MCP server."}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Test Details"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": "Created via Notion API"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": "Part of Phase 1 validation"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": "Tests document creation functionality"}}]
                    }
                }
            ]
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/pages",
                    headers=self.headers,
                    json=create_payload
                )
                
                if response.status_code == 200:
                    page_data = response.json()
                    page_id = page_data["id"]
                    self.test_page_id = page_id
                    print(f"✅ Document created successfully: {page_id}")
                    return page_id
                else:
                    print(f"❌ Document creation failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return None
                    
            except Exception as e:
                print(f"❌ Document creation error: {e}")
                return None
    
    async def test_retrieve_document(self, page_id: str) -> bool:
        """Test document retrieval"""
        print("📖 Testing document retrieval...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Get page properties
                response = await client.get(
                    f"{self.base_url}/pages/{page_id}",
                    headers=self.headers
                )
                
                if response.status_code != 200:
                    print(f"❌ Page retrieval failed: {response.status_code}")
                    return False
                
                page_data = response.json()
                print(f"✅ Page retrieved successfully")
                
                # Get page content
                content_response = await client.get(
                    f"{self.base_url}/blocks/{page_id}/children",
                    headers=self.headers
                )
                
                if content_response.status_code == 200:
                    content_data = content_response.json()
                    print(f"✅ Page content retrieved: {len(content_data.get('results', []))} blocks")
                    return True
                else:
                    print(f"❌ Content retrieval failed: {content_response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"❌ Document retrieval error: {e}")
                return False
    
    async def test_search_documents(self) -> bool:
        """Test database search functionality"""
        print("🔍 Testing document search...")
        
        search_payload = {
            "filter": {
                "property": "Title",
                "title": {"contains": "Test Document"}
            },
            "page_size": 10
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/databases/{self.database_id}/query",
                    headers=self.headers,
                    json=search_payload
                )
                
                if response.status_code == 200:
                    results = response.json()
                    found_docs = results.get("results", [])
                    print(f"✅ Search successful: Found {len(found_docs)} documents")
                    
                    # Test tag-based search
                    tag_search_payload = {
                        "filter": {
                            "property": "Tags",
                            "multi_select": {"contains": "test"}
                        }
                    }
                    
                    tag_response = await client.post(
                        f"{self.base_url}/databases/{self.database_id}/query",
                        headers=self.headers,
                        json=tag_search_payload
                    )
                    
                    if tag_response.status_code == 200:
                        tag_results = tag_response.json()
                        print(f"✅ Tag search successful: Found {len(tag_results.get('results', []))} documents with 'test' tag")
                        return True
                    else:
                        print(f"❌ Tag search failed: {tag_response.status_code}")
                        return False
                        
                else:
                    print(f"❌ Search failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return False
                    
            except Exception as e:
                print(f"❌ Search error: {e}")
                return False
    
    async def test_error_scenarios(self) -> bool:
        """Test error handling scenarios"""
        print("⚠️ Testing error scenarios...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test 1: Invalid API key
            bad_headers = {
                "Authorization": "Bearer invalid_key",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json"
            }
            
            try:
                response = await client.get(
                    f"{self.base_url}/databases/{self.database_id}",
                    headers=bad_headers
                )
                
                if response.status_code == 401:
                    print("✅ Invalid API key properly rejected (401)")
                else:
                    print(f"❌ Expected 401 for invalid key, got {response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"❌ Error scenario test failed: {e}")
                return False
            
            # Test 2: Non-existent database
            try:
                fake_db_id = "00000000-0000-0000-0000-000000000000"
                response = await client.get(
                    f"{self.base_url}/databases/{fake_db_id}",
                    headers=self.headers
                )
                
                if response.status_code == 404:
                    print("✅ Non-existent database properly rejected (404)")
                else:
                    print(f"❌ Expected 404 for fake database, got {response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"❌ Non-existent database test failed: {e}")
                return False
            
            print("✅ All error scenarios handled correctly")
            return True
    
    async def run_all_tests(self) -> bool:
        """Run complete test suite"""
        print("🚀 Starting Notion API Test Suite")
        print("=" * 50)
        
        if not self.secret or self.secret == "YOUR_SECRET_HERE":
            print("❌ NOTION_INTERNAL_INTEGRATION_SECRET not set")
            print("Please set your Notion integration secret as an environment variable")
            return False
        
        if not self.database_id or self.database_id == "YOUR_DATABASE_ID":
            print("❌ NOTION_DATABASE_ID not set")
            print("Please set your Notion database ID as an environment variable")
            return False
        
        # Run tests in sequence
        tests = [
            ("Database Access", self.test_database_access()),
            ("Document Creation", self.test_create_document()),
            ("Document Retrieval", None),  # Will use result from creation
            ("Document Search", self.test_search_documents()),
            ("Error Scenarios", self.test_error_scenarios())
        ]
        
        all_passed = True
        
        for test_name, test_coro in tests:
            print(f"\n📋 Running: {test_name}")
            print("-" * 30)
            
            if test_name == "Document Retrieval":
                if self.test_page_id:
                    result = await self.test_retrieve_document(self.test_page_id)
                else:
                    print("❌ No test page ID available (creation failed)")
                    result = False
            elif test_name == "Document Creation":
                result = await test_coro
                if not result:
                    all_passed = False
                continue
            else:
                result = await test_coro
            
            if not result:
                all_passed = False
                print(f"❌ {test_name} failed")
            else:
                print(f"✅ {test_name} passed")
        
        print("\n" + "=" * 50)
        if all_passed:
            print("🎉 All tests passed! Notion API integration is working correctly.")
            print(f"🔗 Test document created with ID: {self.test_page_id}")
            print("You can view it in your Notion workspace.")
        else:
            print("❌ Some tests failed. Please check the configuration and try again.")
        
        return all_passed

async def main():
    """Main test runner"""
    print("🎯 Notion Document Store MCP - API Test Suite")
    print("This script validates Notion API connectivity and operations")
    print("")
    
    # Display configuration instructions
    if NOTION_SECRET == "YOUR_SECRET_HERE" or DATABASE_ID == "YOUR_DATABASE_ID":
        print("⚙️ CONFIGURATION REQUIRED:")
        print("1. Go to https://www.notion.so/my-integrations")
        print("2. Create a new integration named 'Document Store MCP'")
        print("3. Set capabilities: Read content, Update content, Insert content")
        print("4. Copy the Integration Secret")
        print("5. Create a database in Notion with these properties:")
        print("   - Title (Title type)")
        print("   - Category (Select type) - Add options: General, Code, Tutorial, Reference, Methodology")
        print("   - Tags (Multi-select type)")
        print("   - URL (URL type)")
        print("   - Created (Date type)")
        print("6. Share the database with your integration")
        print("7. Copy the Database ID from the URL")
        print("8. Set environment variables:")
        print("   export NOTION_INTERNAL_INTEGRATION_SECRET='secret_your_secret_here'")
        print("   export NOTION_DATABASE_ID='your-database-id'")
        print("")
        print("❌ Please configure the integration and database first.")
        return
    
    tester = NotionAPITester(NOTION_SECRET, DATABASE_ID)
    success = await tester.run_all_tests()
    
    if success:
        print("\n🔥 Phase 1 validation complete! Ready for Phase 2.")
    else:
        print("\n🚨 Please fix the issues above before proceeding.")

if __name__ == "__main__":
    asyncio.run(main())