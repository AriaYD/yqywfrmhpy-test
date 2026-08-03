/** 口令门共用：HMAC 签名（middleware 与 /api/auth/passcode 同一实现）。 */

const b64url = (bytes: Uint8Array): string =>
  btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export const GATE_COOKIE = "cp_gate";

export async function signGate(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign(
    "HMAC", key, new TextEncoder().encode(payload));
  return b64url(new Uint8Array(sig));
}

export function gatePayload(days = 30): string {
  const body = JSON.stringify({ exp: Date.now() + days * 86_400_000 });
  return btoa(body).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
