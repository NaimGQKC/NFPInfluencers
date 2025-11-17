// app/api/targets/route.ts

import { NextRequest, NextResponse } from 'next/server';
// Import createClient directly
import { createClient } from '@supabase/supabase-js';
// We still need these helpers
import { generateDossierId, normalizeUsername } from '@/lib/supabase';
import { CreateTargetRequest, CreateTargetResponse } from '@/types/dossier';

// Create a new, server-side Supabase client
// Note: We use process.env.SUPABASE_SERVICE_ROLE_KEY, NOT the NEXT_PUBLIC_ one
const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function POST(request: NextRequest) {
  try {
    const body: CreateTargetRequest = await request.json();

    if (!body.username || typeof body.username !== 'string') {
      return NextResponse.json(
        { error: 'Username is required' },
        { status: 400 }
      );
    }

    const username = normalizeUsername(body.username);

    if (!username) {
      return NextResponse.json(
        { error: 'Invalid username' },
        { status: 400 }
      );
    }

    // ... (The rest of your function is perfectly fine!)
    const { data: existing } = await supabase
      .from('targets')
      .select('dossier_id')
      .eq('username', username)
      .maybeSingle();

    if (existing) {
      return NextResponse.json<CreateTargetResponse>({
        dossierId: existing.dossier_id,
      });
    }

    const dossierId = generateDossierId();

    const { data, error } = await supabase
      .from('targets')
      .insert({
        username,
        dossier_id: dossierId,
        last_updated_at: new Date().toISOString(),
      })
      .select('dossier_id')
      .single();

    if (error) {
      console.error('Database error:', error);
      return NextResponse.json(
        { error: 'Failed to create target' },
        { status: 500 }
      );
    }

    return NextResponse.json<CreateTargetResponse>({
      dossierId: data.dossier_id,
    });
  } catch (error) {
    console.error('Unexpected error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}