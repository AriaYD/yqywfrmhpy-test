import { NextRequest, NextResponse } from "next/server";

import { GATE_COOKIE, gatePayload, signGate } from "@/lib/gate";

/**
 * 口令校验（服务端，2026-08-02）。口令只比对运行时环境变量——代码与
 * 快照里没有它；界面上也不再印口令。比对用恒时算法防时序侧信道。
 * 未设 `CAMPUSPATH_DEMO_PASSCODE` 时门不存在，任何提交都放行（本地开发）。
 */
function constantTimeEqual(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  let diff = ea.length ^ eb.length;
  const n = Math.max(ea.length, eb.length);
  for (let i = 0; i < n; i++) diff |= (ea[i] ?? 0) ^ (eb[i] ?? 0);
  return diff === 0;
}

export async function POST(request: NextRequest) {
  const expected = process.env.CAMPUSPATH_DEMO_PASSCODE;
  if (!expected) return NextResponse.json({ ok: true, gate: "off" });

  let given = "";
  try {
    given = String((await request.json())?.passcode ?? "");
  } catch {
    /* 空体当空口令 */
  }
  if (!constantTimeEqual(given, expected)) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const secret = process.env.AUTH_SECRET ?? expected;
  const payload = gatePayload();
  const response = NextResponse.json({ ok: true });
  response.cookies.set(GATE_COOKIE, `${payload}.${await signGate(payload, secret)}`, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    maxAge: 30 * 86_400,
    path: "/",
  });
  return response;
}
