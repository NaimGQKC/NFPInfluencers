'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  AlertCircle,
  Calendar,
  ChevronDown,
  ChevronUp,
  FileText,
  Image as ImageIcon,
  Loader2,
  Shield,
  Video,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { DossierResponse, Story } from '@/types/dossier';

export default function DossierPage() {
  const params = useParams();
  const dossierId = params.dossierId as string;

  const [dossier, setDossier] = useState<DossierResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedStories, setExpandedStories] = useState<Set<string>>(
    new Set()
  );

  useEffect(() => {
    const fetchDossier = async () => {
      try {
        const response = await fetch(`/api/dossier/${dossierId}`);

        if (!response.ok) {
          if (response.status === 404) {
            throw new Error(
              'Dossier not found. Please check your URL or wait for the system to collect the first stories.'
            );
          }
          throw new Error('Failed to load dossier');
        }

        const data: DossierResponse = await response.json();
        setDossier(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    };

    fetchDossier();
  }, [dossierId]);

  const toggleStory = (storyId: string) => {
    setExpandedStories((prev) => {
      const next = new Set(prev);
      if (next.has(storyId)) {
        next.delete(storyId);
      } else {
        next.add(storyId);
      }
      return next;
    });
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-slate-600 mx-auto mb-4" />
          <p className="text-slate-600">Loading dossier...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
        <div className="max-w-2xl mx-auto px-4 py-12">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <div className="mt-6 text-center">
            <a href="/">
              <Button>Return to Home</Button>
            </a>
          </div>
        </div>
      </div>
    );
  }

  if (!dossier) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-full bg-slate-900 text-white flex items-center justify-center">
              <Shield className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">LeviProof</h1>
              <p className="text-sm text-slate-600">Evidence Dossier</p>
            </div>
          </div>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Target: @{dossier.username}</span>
              <span className="text-sm font-normal text-slate-600">
                {dossier.storyCount} stories analyzed
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-slate-600">Dossier Created</p>
                <p className="font-medium">{formatDate(dossier.createdAt)}</p>
              </div>
              <div>
                <p className="text-slate-600">Last Updated</p>
                <p className="font-medium">
                  {formatDate(dossier.lastUpdatedAt)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Alert className="mb-6 bg-amber-50 border-amber-200">
          <AlertCircle className="h-4 w-4 text-amber-600" />
          <AlertTitle className="text-amber-900">
            Important Reminder
          </AlertTitle>
          <AlertDescription className="text-amber-900">
            We do not store your personal proof. To report this to regulators,
            combine this analysis with your own screenshots, DMs, and receipts
            when filing complaints with the Competition Bureau, OSC, or CAFC.
          </AlertDescription>
        </Alert>

        {dossier.storyCount === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <FileText className="w-12 h-12 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                No Stories Yet
              </h3>
              <p className="text-slate-600 max-w-md mx-auto">
                The system is monitoring @{dossier.username}. Stories will
                appear here as they are collected and analyzed. Check back in a
                few hours.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-slate-900">
              Story Analysis Timeline
            </h2>

            {dossier.stories.map((story) => (
              <StoryCard
                key={story.id}
                story={story}
                expanded={expandedStories.has(story.id)}
                onToggle={() => toggleStory(story.id)}
              />
            ))}
          </div>
        )}

        <div className="mt-8 text-center text-xs text-slate-500">
          <p>
            LeviProof is an open-source public utility. This analysis is for
            informational purposes only.
          </p>
        </div>
      </div>
    </div>
  );
}

function StoryCard({
  story,
  expanded,
  onToggle,
}: {
  story: Story;
  expanded: boolean;
  onToggle: () => void;
}) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3 flex-1">
            <div className="flex-shrink-0">
              {story.mediaType === 'video' ? (
                <div className="w-10 h-10 rounded bg-slate-200 flex items-center justify-center">
                  <Video className="w-5 h-5 text-slate-600" />
                </div>
              ) : (
                <div className="w-10 h-10 rounded bg-slate-200 flex items-center justify-center">
                  <ImageIcon className="w-5 h-5 text-slate-600" />
                </div>
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <Calendar className="w-4 h-4 text-slate-500" />
                <span className="text-sm text-slate-600">
                  {formatDate(story.timestamp)}
                </span>
              </div>
              <div className="text-sm text-slate-700 mt-2">
                <div
                  dangerouslySetInnerHTML={{
                    __html: story.summary.replace(/\n/g, '<br />'),
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <>
          <Separator />
          <CardContent className="pt-4">
            <h4 className="font-semibold text-slate-900 mb-2">
              Full Legal Analysis
            </h4>
            <div className="bg-slate-50 rounded-lg p-4 text-sm text-slate-700 whitespace-pre-wrap font-mono">
              {story.fullAnalysis}
            </div>
          </CardContent>
        </>
      )}

      <Separator />
      <CardContent className="py-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggle}
          className="w-full justify-center text-slate-600 hover:text-slate-900"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-4 h-4 mr-1" />
              Hide Full Analysis
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4 mr-1" />
              View Full Analysis
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
