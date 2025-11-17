export type MediaType = "image" | "video";

export type Story = {
  id: string;
  timestamp: string;
  mediaType: MediaType;
  mediaUrl?: string;
  summary: string;
  fullAnalysis: string;
};

export type DossierResponse = {
  dossierId: string;
  username: string;
  createdAt: string;
  lastUpdatedAt: string;
  storyCount: number;
  stories: Story[];
};

export type Target = {
  id: string;
  username: string;
  dossierId: string;
  createdAt: string;
  lastUpdatedAt: string;
};

export type CreateTargetRequest = {
  username: string;
};

export type CreateTargetResponse = {
  dossierId: string;
};
