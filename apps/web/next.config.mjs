/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Transpile the shared workspace package so its TS is compiled by Next.
  transpilePackages: ["@lead-recovery/shared"],
};

export default nextConfig;
