/** Public catalog read client. This is NOT generated from the five service OpenAPI contracts yet. */
export type Listing = {
  id: string;
  slug: string;
  title: string;
  description: string;
  price: string;
  currency: string;
  status: string;
};

export async function publicListings(): Promise<Listing[]> {
  const url = process.env.MARKETPLACE_API_URL;
  if (!url) return [];
  // URL is operator-supplied environment config, never user-controlled input.
  const response = await fetch(new URL('/api/listings/', url), {
    cache: 'no-store',
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error('Catalog API unavailable');
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) throw new Error('Invalid catalog response');
  return parsed as Listing[];
}
