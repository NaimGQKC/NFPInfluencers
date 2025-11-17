import { NextRequest, NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';
import { DossierResponse, Story } from '@/types/dossier';

export async function GET(
  request: NextRequest,
  { params }: { params: { dossierId: string } }
) {
  try {
    const { dossierId } = params;

    const { data: target, error: targetError } = await supabase
      .from('targets')
      .select('*')
      .eq('dossier_id', dossierId)
      .maybeSingle();

    if (targetError || !target) {
      return NextResponse.json(
        { error: 'Dossier not found' },
        { status: 404 }
      );
    }

    const { data: stories, error: storiesError } = await supabase
      .from('stories')
      .select('*')
      .eq('target_id', target.id)
      .order('timestamp', { ascending: false });

    if (storiesError) {
      console.error('Error fetching stories:', storiesError);
      return NextResponse.json(
        { error: 'Failed to fetch stories' },
        { status: 500 }
      );
    }

    const response: DossierResponse = {
      dossierId: target.dossier_id,
      username: target.username,
      createdAt: target.created_at,
      lastUpdatedAt: target.last_updated_at,
      storyCount: stories?.length || 0,
      stories:
        stories?.map(
          (story): Story => ({
            id: story.id,
            timestamp: story.timestamp,
            mediaType: story.media_type as 'image' | 'video',
            mediaUrl: story.media_url,
            summary: story.summary,
            fullAnalysis: story.full_analysis,
          })
        ) || [],
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Unexpected error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
