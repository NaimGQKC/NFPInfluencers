/*
  # LeviProof Database Schema

  1. New Tables
    - `targets`
      - `id` (uuid, primary key)
      - `username` (text, unique) - Instagram username without @
      - `dossier_id` (text, unique) - Random unguessable URL slug
      - `created_at` (timestamptz)
      - `last_updated_at` (timestamptz)
      
    - `stories`
      - `id` (uuid, primary key)
      - `target_id` (uuid, foreign key to targets)
      - `story_id` (text) - Instagram story ID
      - `timestamp` (timestamptz) - When story was posted
      - `media_type` (text) - "image" or "video"
      - `media_url` (text, nullable) - Path or URL to media file
      - `summary` (text) - Short bullet-style summary
      - `full_analysis` (text) - Complete analysis text
      - `created_at` (timestamptz)

  2. Security
    - Enable RLS on both tables
    - Public read access (no auth required) - zero-knowledge design
    - No write policies for public (backend only)

  3. Important Notes
    - This is a zero-knowledge system: no user PII stored
    - All data is public Instagram content + analysis
    - dossier_id must be unguessable (entropy ~60 bits)
*/

CREATE TABLE IF NOT EXISTS targets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text UNIQUE NOT NULL,
  dossier_id text UNIQUE NOT NULL,
  created_at timestamptz DEFAULT now(),
  last_updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  target_id uuid NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  story_id text NOT NULL,
  timestamp timestamptz NOT NULL,
  media_type text NOT NULL DEFAULT 'video',
  media_url text,
  summary text NOT NULL DEFAULT '',
  full_analysis text NOT NULL DEFAULT '',
  created_at timestamptz DEFAULT now(),
  UNIQUE(target_id, story_id)
);

CREATE INDEX IF NOT EXISTS idx_targets_dossier_id ON targets(dossier_id);
CREATE INDEX IF NOT EXISTS idx_stories_target_id ON stories(target_id);
CREATE INDEX IF NOT EXISTS idx_stories_timestamp ON stories(target_id, timestamp DESC);

ALTER TABLE targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE stories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read access to targets"
  ON targets FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public read access to stories"
  ON stories FOR SELECT
  TO anon, authenticated
  USING (true);