# 🎯 Notion Integration Setup Guide

This guide walks you through setting up the Notion integration and database for the Document Store MCP server.

## 📋 Step 1: Create Notion Integration

1. **Go to Notion Integrations**
   - Visit: https://www.notion.so/my-integrations
   - Click "New integration"

2. **Configure Integration**
   - **Name**: `Document Store MCP`
   - **Associated workspace**: Select your workspace
   - **Capabilities**: 
     - ✅ Read content
     - ✅ Update content  
     - ✅ Insert content
   - **User Capabilities**: No additional capabilities needed

3. **Save and Copy Secret**
   - Click "Submit"
   - Copy the **Internal Integration Secret** (starts with `secret_`)
   - ⚠️ Keep this secret secure - treat it like a password

## 📋 Step 2: Create Document Database

1. **Create New Page**
   - In your Notion workspace, create a new page
   - Title it: `Document Store`

2. **Add Database**
   - Type `/database` and select "Table - Full page"
   - Configure the following properties exactly:

### Required Database Properties:

| Property Name | Property Type | Configuration |
|---------------|---------------|---------------|
| **Title** | Title | (Default - already exists) |
| **Category** | Select | Add options: `General`, `Code`, `Tutorial`, `Reference`, `Methodology` |
| **Tags** | Multi-select | (No pre-defined options needed) |
| **URL** | URL | (No additional config) |
| **Created** | Date | (No additional config) |

3. **Property Setup Details**:
   
   **Category (Select)**:
   - Click the property dropdown → Edit property
   - Add these exact options:
     - `General` (default)
     - `Code`
     - `Tutorial` 
     - `Reference`
     - `Methodology`
   
   **Tags (Multi-select)**:
   - No pre-defined options needed
   - Tags will be created dynamically when documents are added

## 📋 Step 3: Share Database with Integration

1. **Share the Database**
   - Click "Share" button in top-right
   - Click "Invite"
   - Search for: `Document Store MCP` (your integration name)
   - Select the integration from dropdown
   - Set permissions to: **Can edit**
   - Click "Invite"

2. **Verify Integration Access**
   - The integration should now appear in the "People with access" list
   - Permission should show "Can edit"

## 📋 Step 4: Get Database ID

1. **Copy Database ID from URL**
   - The URL will look like: `https://www.notion.so/username/DATABASE_ID?v=...`
   - Copy the `DATABASE_ID` part (32-character string with dashes)
   - Example: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`

## 📋 Step 5: Configure Environment Variables

Create a `.env` file in your project root with:

```bash
# Notion API Configuration
NOTION_INTERNAL_INTEGRATION_SECRET=secret_your_integration_secret_here
NOTION_DATABASE_ID=your-database-id-here
NOTION_API_VERSION=2022-06-28
```

**Load environment variables**:
```bash
source .env
export $(cat .env | xargs)
```

## 📋 Step 6: Test the Integration

Run the test script to verify everything is working:

```bash
cd notion-document-store
python test_notion_api.py
```

**Expected output**:
```
🎯 Notion Document Store MCP - API Test Suite
🚀 Starting Notion API Test Suite
==================================================

📋 Running: Database Access
------------------------------
✅ Database access successful: Document Store
✅ All required properties found

📋 Running: Document Creation
------------------------------
✅ Document created successfully: a1b2c3d4-e5f6-7890-abcd-ef1234567890

📋 Running: Document Retrieval
------------------------------
✅ Page retrieved successfully
✅ Page content retrieved: 5 blocks

📋 Running: Document Search
------------------------------
✅ Search successful: Found 1 documents
✅ Tag search successful: Found 1 documents with 'test' tag

📋 Running: Error Scenarios
------------------------------
✅ Invalid API key properly rejected (401)
✅ Non-existent database properly rejected (404)
✅ All error scenarios handled correctly

==================================================
🎉 All tests passed! Notion API integration is working correctly.
🔗 Test document created with ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
You can view it in your Notion workspace.

🔥 Phase 1 validation complete! Ready for Phase 2.
```

## 🔧 Troubleshooting

### ❌ Database access failed (401)
- **Issue**: Invalid integration secret
- **Solution**: Double-check the `NOTION_INTERNAL_INTEGRATION_SECRET` value
- **Check**: Make sure it starts with `secret_`

### ❌ Database access failed (404)  
- **Issue**: Database not found or not shared with integration
- **Solution**: 
  1. Verify the `NOTION_DATABASE_ID` is correct
  2. Ensure the database is shared with your integration
  3. Check that the integration has "Can edit" permissions

### ❌ Missing required properties
- **Issue**: Database doesn't have all required properties
- **Solution**: Add the missing properties as specified in Step 2

### ❌ Document creation failed (400)
- **Issue**: Invalid database schema or property values
- **Solution**: 
  1. Check that Category has the required select options
  2. Verify all property types match the specification
  3. Ensure the integration has write permissions

## ✅ Success Criteria

✅ Integration created with proper capabilities  
✅ Database created with all required properties  
✅ Database shared with integration (Can edit permissions)  
✅ Test script runs successfully and creates test document  
✅ Test document visible in Notion workspace  
✅ All API operations (Create, Read, Search) working  

## 🎯 Next Steps

Once all tests pass, you're ready to proceed to **Phase 2: Core MCP Server Development**!

The Notion foundation is now solid and ready for the MCP server implementation.