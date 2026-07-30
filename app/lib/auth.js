/** lib/auth.js — MAC/Tailscale-gated passkey
 *  Passkey = SHA-256(primary MAC | hostname | SALT). MAC here is an
 *  obfuscation gate (not cryptographic auth) — fine for a status page limited
 *  to this box / Tailscale. Set STATUS_SALT in Vercel env to harden it.
 */
import crypto from "crypto";

// OMEN-01 adapter MACs (primary first).
export const ALLOWED_MACS = [
  "30-24-A9-7F-6E-32",
  "DC-41-A9-6B-89-CA",
  "DE-41-A9-6B-89-C9",
  "DC-41-A9-6B-89-C9",
].map((m) => m.toLowerCase().replace(/[:-]/g, ""));

export const HOSTNAME = "omen-01";

export function derivePasskey(salt = process.env.STATUS_SALT || "somacosf-2026") {
  const mac = ALLOWED_MACS[0];
  return crypto.createHash("sha256").update(`${mac}|${HOSTNAME}|${salt}`).digest("hex");
}

export function checkPasskey(candidate, salt = process.env.STATUS_SALT || "somacosf-2026") {
  if (!candidate) return false;
  const a = Buffer.from(candidate);
  const b = Buffer.from(derivePasskey(salt));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
