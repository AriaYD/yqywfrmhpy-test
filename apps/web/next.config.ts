import type { NextConfig } from "next";

/**
 * 前端与 API 同源：`/api/v1/*` 反向代理到 FastAPI。
 *
 * 这样浏览器不需要 CORS，API 也不必为了一个演示前端放开跨域——
 * 少一处需要有人记得收回去的放宽。
 */
const API_ORIGIN = process.env.CAMPUSPATH_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  /**
   * 浏览器实测走 `127.0.0.1`，而 dev server 默认只认 `localhost`——
   * 于是 `/_next/*` 被当成跨源请求拦掉，结果是**整页静默不 hydrate**：
   * SSR 的 HTML 照常显示，看着完全正常，但 effect 不跑、onClick 无效，
   * 浏览器控制台里只有一条 websocket 失败，没有任何红字。
   * 只在 dev 生效，不影响生产构建。
   */
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
