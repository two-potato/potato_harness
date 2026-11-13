/** @type {import('next').NextConfig} */
// Only trusted loopback backend URLs are supported in this development scaffold.
// All mutating browser requests use this same-origin /api rewrite, so Django
// session cookies and CSRF tokens are never forwarded to arbitrary hosts.
const backend = process.env.MARKETPLACE_API_URL;
if (backend && !/^http:\/\/(?:127\.0\.0\.1|localhost):[0-9]{2,5}$/.test(backend)) {
  throw new Error('Development backend must be an explicit local loopback HTTP origin');
}
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Django owns /api routes with and without a trailing slash. Next must not
  // issue a 308 redirect before forwarding mutating requests or CSRF checks.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return backend ? [{source:'/api/:path*',destination:`${backend}/api/:path*`}] : [];
  },
};
export default nextConfig;
