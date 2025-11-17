# Backend Integration Guide

This document explains how to integrate your existing Python backend with the LeviProof frontend.

## Current Setup (Recommended)

The frontend currently uses **direct Supabase database access**. This is the simplest integration path:

### Python Backend → Supabase Database ← Frontend

Your Python services write to Supabase tables, and the frontend reads from them.

## Integration Steps

### 1. Install Supabase Python Client

```bash
pip install supabase
```

### 2. Configure Python Services

Add to your Python backend:

```python
import os
from supabase import create_client, Client

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Use service role for writes
supabase: Client = create_client(supabase_url, supabase_key)
```

### 3. Update ig_scraper.py

When creating a new target:

```python
def create_target(username: str) -> str:
    """Create a new target and return the dossier_id"""
    import secrets
    import string

    # Generate random dossier ID
    chars = string.ascii_letters + string.digits
    dossier_id = ''.join(secrets.choice(chars) for _ in range(12))

    # Insert into Supabase
    data = supabase.table('targets').insert({
        'username': username.lower().strip().replace('@', ''),
        'dossier_id': dossier_id,
        'last_updated_at': 'now()'
    }).execute()

    return dossier_id
```

When saving story media:

```python
def save_story(target_username: str, story_data: dict):
    """Save story to database"""

    # Get target_id from username
    target = supabase.table('targets').select('id').eq('username', target_username).single().execute()
    target_id = target.data['id']

    # Insert story
    supabase.table('stories').insert({
        'target_id': target_id,
        'story_id': story_data['story_id'],
        'timestamp': story_data['taken_at'],
        'media_type': 'video' if story_data['is_video'] else 'image',
        'media_url': story_data['local_path'],  # or remote URL
        'summary': '',  # Will be filled by investigator_agent
        'full_analysis': ''
    }).execute()
```

### 4. Update investigator_agent.py

When generating analysis:

```python
def analyze_story(story_id: str, transcript: str, legal_analysis: str):
    """Update story with analysis"""

    # Generate summary (extract first few bullet points)
    summary = generate_summary(legal_analysis)

    # Update story in database
    supabase.table('stories').update({
        'summary': summary,
        'full_analysis': legal_analysis,
    }).eq('story_id', story_id).execute()

    # Update target's last_updated_at
    story = supabase.table('stories').select('target_id').eq('story_id', story_id).single().execute()
    supabase.table('targets').update({
        'last_updated_at': 'now()'
    }).eq('id', story.data['target_id']).execute()
```

### 5. Update collector_daemon.py

No changes needed - just ensure it calls the updated `ig_scraper` and `investigator_agent` functions.

## Environment Variables

Add to your Python `.env`:

```bash
SUPABASE_URL=https://ghizyrcnnaosuyizyjkp.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
```

⚠️ **Important**: Use the **service role key** for backend writes, not the anon key.

## Alternative: HTTP API Approach

If you prefer to expose a REST API from Python instead of direct database access:

### 1. Create Python API Endpoints

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/api/targets")
async def create_target_endpoint(request: dict):
    username = request['username']
    dossier_id = create_target(username)  # Your existing logic
    return {"dossierId": dossier_id}

@app.get("/api/dossier/{dossier_id}")
async def get_dossier(dossier_id: str):
    # Fetch from Supabase or your database
    target = supabase.table('targets').select('*').eq('dossier_id', dossier_id).single().execute()
    stories = supabase.table('stories').select('*').eq('target_id', target.data['id']).execute()

    return {
        "dossierId": target.data['dossier_id'],
        "username": target.data['username'],
        "createdAt": target.data['created_at'],
        "lastUpdatedAt": target.data['last_updated_at'],
        "storyCount": len(stories.data),
        "stories": [
            {
                "id": s['id'],
                "timestamp": s['timestamp'],
                "mediaType": s['media_type'],
                "mediaUrl": s['media_url'],
                "summary": s['summary'],
                "fullAnalysis": s['full_analysis']
            }
            for s in stories.data
        ]
    }
```

### 2. Update Frontend API Routes

In `app/api/targets/route.ts`:

```typescript
export async function POST(request: NextRequest) {
  const body = await request.json();

  // Replace Supabase with HTTP call
  const response = await fetch(`${process.env.PYTHON_BACKEND_URL}/api/targets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  const data = await response.json();
  return NextResponse.json(data);
}
```

In `app/api/dossier/[dossierId]/route.ts`:

```typescript
export async function GET(
  request: NextRequest,
  { params }: { params: { dossierId: string } }
) {
  const response = await fetch(
    `${process.env.PYTHON_BACKEND_URL}/api/dossier/${params.dossierId}`
  );

  if (!response.ok) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  const data = await response.json();
  return NextResponse.json(data);
}
```

### 3. Add Environment Variable

In `.env`:
```bash
PYTHON_BACKEND_URL=http://localhost:8000
```

## Recommendation

**Use the direct database approach** (first option). It's simpler and avoids unnecessary HTTP overhead. Your Python services and frontend can both read/write to Supabase independently.

The HTTP API approach only makes sense if:
- You have complex business logic that needs to stay in Python
- You want to add caching/rate limiting at the API layer
- You have compliance requirements for API-based access

## Testing the Integration

1. Run your Python scraper to create a target
2. Check that it appears in Supabase `targets` table
3. Visit the frontend and verify the dossier URL works
4. Run your analyzer to add story analysis
5. Refresh the dossier page and verify stories appear

## Database Schema Reference

### Targets Table
```sql
CREATE TABLE targets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text UNIQUE NOT NULL,
  dossier_id text UNIQUE NOT NULL,
  created_at timestamptz DEFAULT now(),
  last_updated_at timestamptz DEFAULT now()
);
```

### Stories Table
```sql
CREATE TABLE stories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  target_id uuid REFERENCES targets(id) ON DELETE CASCADE,
  story_id text NOT NULL,
  timestamp timestamptz NOT NULL,
  media_type text DEFAULT 'video',
  media_url text,
  summary text DEFAULT '',
  full_analysis text DEFAULT '',
  created_at timestamptz DEFAULT now(),
  UNIQUE(target_id, story_id)
);
```

## Troubleshooting

### "Row Level Security" errors
Make sure you're using the **service role key** in Python, not the anon key.

### Stories not appearing
Check that:
1. `target_id` foreign key is correct
2. `timestamp` is a valid ISO timestamp
3. `summary` and `full_analysis` are populated

### Dossier URL returns 404
Verify the `dossier_id` exactly matches what's in the database (case-sensitive).

## Questions?

Check the main README.md or examine the existing API routes in `app/api/` for reference implementations.
