'use client';

import { useState } from 'react';
import { AlertCircle, CheckCircle2, Copy, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';

export default function Home() {
  const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [dossierId, setDossierId] = useState('');
  const [copied, setCopied] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setDossierId('');

    if (!username.trim()) {
      setError('Please enter an Instagram username');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch('/api/targets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim() }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to create dossier');
      }

      const data = await response.json();
      setDossierId(data.dossierId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const dossierUrl = dossierId
    ? `${window.location.origin}/dossier/${dossierId}`
    : '';

  const copyToClipboard = () => {
    navigator.clipboard.writeText(dossierUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="max-w-2xl mx-auto px-4 py-12">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-900 text-white mb-4">
            <Shield className="w-8 h-8" />
          </div>
          <h1 className="text-4xl font-bold text-slate-900 mb-2">
            LeviProof
          </h1>
          <p className="text-lg text-slate-600">
            Zero-Knowledge Finfluencer Evidence Portal
          </p>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-xl">How It Works</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600">
            <div className="flex gap-3">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-slate-700 font-semibold">
                1
              </div>
              <p>
                <strong className="text-slate-900">We only watch public content.</strong> Our system
                continuously monitors public Instagram stories from the influencer you report.
              </p>
            </div>
            <div className="flex gap-3">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-slate-700 font-semibold">
                2
              </div>
              <p>
                <strong className="text-slate-900">We never store your identity.</strong> No emails,
                no names, no personal information. This is a zero-knowledge public utility.
              </p>
            </div>
            <div className="flex gap-3">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-slate-700 font-semibold">
                3
              </div>
              <p>
                <strong className="text-slate-900">You combine the evidence.</strong> Use the dossier
                output + your own private proof (DMs, receipts) to file complaints with Canadian
                regulators (Competition Bureau, OSC, CAFC).
              </p>
            </div>
          </CardContent>
        </Card>

        {!dossierId ? (
          <Card>
            <CardHeader>
              <CardTitle>Start Anonymous Dossier</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label
                    htmlFor="username"
                    className="block text-sm font-medium text-slate-700 mb-2"
                  >
                    Instagram Username
                  </label>
                  <Input
                    id="username"
                    type="text"
                    placeholder="@username or username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={loading}
                    className="text-lg"
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Enter the influencer's Instagram handle
                  </p>
                </div>

                {error && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? 'Creating Dossier...' : 'Start Anonymous Dossier'}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-2 border-green-200 bg-green-50">
            <CardHeader>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-6 h-6 text-green-600" />
                <CardTitle className="text-green-900">
                  Dossier Created
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert className="bg-amber-50 border-amber-200">
                <AlertCircle className="h-4 w-4 text-amber-600" />
                <AlertDescription className="text-amber-900">
                  <strong>Important:</strong> We cannot recover this URL. Bookmark or
                  save it now. This is your only way to access the dossier.
                </AlertDescription>
              </Alert>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Your Private Dossier URL
                </label>
                <div className="flex gap-2">
                  <Input
                    type="text"
                    value={dossierUrl}
                    readOnly
                    className="font-mono text-sm bg-white"
                  />
                  <Button
                    onClick={copyToClipboard}
                    variant="outline"
                    size="icon"
                    className="flex-shrink-0"
                  >
                    {copied ? (
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="pt-2">
                <a href={dossierUrl}>
                  <Button className="w-full">View Dossier</Button>
                </a>
              </div>

              <div className="text-sm text-slate-600 space-y-1">
                <p>
                  The system will begin collecting and analyzing public Instagram stories
                  from @{username}. Check back periodically as new evidence is gathered.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="mt-8 text-center text-xs text-slate-500">
          <p>
            LeviProof is an open-source public utility. We do not provide legal
            advice.
          </p>
          <p className="mt-1">
            Report findings to:{' '}
            <a
              href="https://www.competitionbureau.gc.ca/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-slate-700"
            >
              Competition Bureau
            </a>
            ,{' '}
            <a
              href="https://www.osc.ca/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-slate-700"
            >
              OSC
            </a>
            ,{' '}
            <a
              href="https://www.antifraudcentre-centreantifraude.ca/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-slate-700"
            >
              CAFC
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
