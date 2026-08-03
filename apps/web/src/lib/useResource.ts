"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

export type Resource<T> = {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  reload: () => void;
};

/**
 * 会话级缓存（2026-08-03 用户报障：For You 每次切回都要等骨架屏重刷，
 * 而服务端明明有当日缓存——慢的不是计算是"每次挂载都从零等一趟网络"）。
 * 模块级 Map 随 SPA 存活：命中先上屏，后台照常请求、回来静默替换
 * （stale-while-revalidate）。整页刷新即清空，不存磁盘。
 *
 * key = cacheKey + deps。纪律：load 闭包里的**每个**请求入参都必须出现在
 * cacheKey 或 deps 里（例如 "catalog-500" 把 limit 编进了名字）——
 * 否则两个不同请求会互相串数据（审查 M-4）。
 */
const CACHE = new Map<string, unknown>();

/** 登出/换人时清空（providers.persist 调用）——残留跨身份是泄漏的前身。 */
export function clearResourceCache(): void {
  CACHE.clear();
}

/**
 * 一个数据源的三态：加载中 / 有数据 / 有错误。
 *
 * 刻意**不把 404 和 503 吞成空数组**——那是"会被信以为真的谎"，
 * 后端为此专门不返回 `[]`（见 app.py 顶部注释）。前端把这个区分带到界面上。
 * 缓存下同样成立：核新遇 404 = 这份数据**已不存在**，缓存与屏上数据一并
 * 清掉（审查 M-1）；503/网络错保留旧数据 + 报错误——降级可见，不可假装没事。
 */
export function useResource<T>(
  load: () => Promise<T>,
  deps: readonly unknown[],
  options?: { cacheKey?: string },
): Resource<T> {
  const key =
    options?.cacheKey != null
      ? `${options.cacheKey}|${deps.map(String).join("␟")}`
      : null;
  const initial = key !== null && CACHE.has(key) ? (CACHE.get(key) as T) : null;
  const [data, setData] = useState<T | null>(initial);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(initial === null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    const hit = key !== null && CACHE.has(key);
    if (hit) {
      // 命中：立即上屏，后台核新
      setData(CACHE.get(key as string) as T);
      setLoading(false);
    } else {
      // miss（含换人/换档导致的 key 变化）：旧 key 的数据不许陪跑（审查 L-8）
      setData(null);
      setLoading(true);
    }
    setError(null);
    load()
      .then((value) => {
        if (!cancelled) {
          // 写缓存也受 cancelled 守卫：乱序的旧响应不许覆盖新结果（审查 M-2）
          if (key !== null) CACHE.set(key, value);
          setData(value);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            // 404 是权威答案「已不存在」——清缓存清屏，不留旧影（审查 M-1）
            if (key !== null) CACHE.delete(key);
            setData(null);
          } else if (!hit) {
            setData(null);
          }
          setError(err);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // load 每次渲染都是新函数，靠调用方给的 deps 决定何时重取
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
