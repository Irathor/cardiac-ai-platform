import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";

interface HealthStatus {
  status: string;
}

export function useBackendLiveness() {
  return useQuery({
    queryKey: ["health", "live"],
    queryFn: () => apiGet<HealthStatus>("/health/live"),
  });
}
