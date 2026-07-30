/** pages/api/status.js — gated status endpoint.
 *  Server-side gate: caller must send header `x-passkey` matching the derived
 *  passkey, OR be on the Tailscale CIDR allowlist. Returns JSON status.
 */
import { checkPasskey } from "../../lib/auth";
import { collectStatus } from "../../lib/status";

export default async function handler(req, res) {
  const pk = req.headers["x-passkey"] || req.query.passkey || "";
  if (!checkPasskey(pk)) {
    return res.status(401).json({ error: "unauthorized" });
  }
  const status = await collectStatus();
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json(status);
}
