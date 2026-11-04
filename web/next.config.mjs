/** @type {import('next').NextConfig} */
const nextConfig = {
  // The PDF reader (pdfjs-dist) can optionally use a "canvas" package on servers; the browser build does not need it.
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
  // Security headers on every page. (The site is plain text and forms, so a strict policy is cheap.)
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
