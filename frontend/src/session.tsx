import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Me } from "./api";

interface SessionValue { me: Me | null; loading: boolean; refresh: () => void; orgId: string | null }
const SessionContext = createContext<SessionValue>({ me: null, loading: true, refresh: () => {}, orgId: null });

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try { return await api.get<Me>("/auth/me"); }
      catch (e) { if (e instanceof ApiError && e.status === 401) return null; throw e; }
    },
    staleTime: 60_000,
  });
  const me = q.data ?? null;
  const stored = localStorageGet("wd_org");
  const orgId = me ? (me.organizations.find((o) => o.id === stored)?.id ?? me.organizations[0]?.id ?? null) : null;
  return (
    <SessionContext.Provider value={{ me, loading: q.isLoading, orgId, refresh: () => qc.invalidateQueries() }}>
      {children}
    </SessionContext.Provider>
  );
}

export const useSession = () => useContext(SessionContext);

export function localStorageGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
export function localStorageSet(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch { /* private mode: ignore */ }
}
