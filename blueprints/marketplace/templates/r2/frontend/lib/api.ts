/** Public catalog read client. Not yet generated from the five R1 OpenAPI contracts. */
export type Listing = {
  id: string;
  slug: string;
  title: string;
  description: string;
  price: string;
  currency: string;
  status: 'DRAFT' | 'PENDING_REVIEW' | 'PUBLISHED' | 'REJECTED';
  content_revision: number;
  approved_revision: number | null;
};

export async function publicListings(): Promise<Listing[]> {
  // The public storefront fetches only the Django-authorized list through a
  // fixed trusted-host URL. Never expose private session cookies to this fetch.
  const url = process.env.MARKETPLACE_API_URL;
  if (!url) return [];
  const response = await fetch(new URL('/api/listings/', url), {
    cache: 'no-store', signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error('Catalog API unavailable');
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) throw new Error('Invalid catalog response');
  return parsed as Listing[];
}
