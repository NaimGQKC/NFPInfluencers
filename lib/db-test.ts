import { supabase } from './supabase';

export async function testDatabaseConnection() {
  try {
    const { data: targets, error: targetsError } = await supabase
      .from('targets')
      .select('username, dossier_id, created_at')
      .limit(5);

    if (targetsError) {
      console.error('Error fetching targets:', targetsError);
      return false;
    }

    console.log('✅ Database connection successful');
    console.log(`Found ${targets?.length || 0} targets:`, targets);

    const { data: stories, error: storiesError } = await supabase
      .from('stories')
      .select('id, target_id, timestamp')
      .limit(5);

    if (storiesError) {
      console.error('Error fetching stories:', storiesError);
      return false;
    }

    console.log(`Found ${stories?.length || 0} stories:`, stories);
    return true;
  } catch (error) {
    console.error('Database connection test failed:', error);
    return false;
  }
}
