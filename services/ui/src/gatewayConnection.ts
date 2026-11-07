import { useEffect, useState } from "react";
import { api } from "./api";

export type GatewayModel = { id: string; provider: string; model: string };
export type GatewayConnection = {
  base_url: string;
  state: "not_configured" | "unavailable" | "no_models" | "ready";
  models: string[];
  catalog: GatewayModel[];
  catalog_warning: string | null;
};

/** Share a fresh gateway catalog between onboarding and key creation. */
export function useGatewayConnection(
  tenant: string,
  revision: number,
  enabled: boolean,
) {
  const [connection, setConnection] = useState<GatewayConnection | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setConnection(null);
    setError("");
    if (!enabled) return;
    api<GatewayConnection>("/gateway/connection", tenant)
      .then((value) => {
        if (active) setConnection(value);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, enabled]);
  return { connection, error };
}
