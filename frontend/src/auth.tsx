import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { api } from "@/api/client";
import type { Me } from "@/api/types";

interface AuthValue {
  me: Me | undefined;
  loading: boolean;
  refresh: () => Promise<unknown>;
  setMe: (me: Me) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue>(null as unknown as AuthValue);

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("auth/me"), staleTime: 60_000 });

  useEffect(() => {
    const onExpired = () => client.invalidateQueries({ queryKey: ["me"] });
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, [client]);

  const value: AuthValue = {
    me: query.data,
    loading: query.isLoading,
    refresh: () => query.refetch(),
    setMe: (me) => client.setQueryData(["me"], me),
    logout: async () => {
      await api.post("auth/logout");
      client.clear();
      client.setQueryData(["me"], { authenticated: false });
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
