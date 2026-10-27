import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, qs } from "./client";
import type { AuthConfig, Dashboard, Meta, Paged, PeriodsPage, ReportKey, ReportSummary, User, Version } from "./types";

const hasProcessing = (rows: { status?: string; latest?: { status: string } | null }[] = []) =>
  rows.some((r) => r.status === "processing" || r.latest?.status === "processing");

export const useAuthConfig = () =>
  useQuery({ queryKey: ["auth-config"], queryFn: () => api<AuthConfig>("/api/auth/config"), staleTime: Infinity });

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: () => api<User>("/api/auth/me"), retry: false, staleTime: 5 * 60_000 });

export const useMeta = () =>
  useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/api/meta"), refetchInterval: 60_000 });

export const useDashboard = () =>
  useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/api/dashboard"),
    refetchInterval: (q) =>
      q.state.data && (hasProcessing(q.state.data.recent) || q.state.data.reports.some((r) => r.current.status === "processing"))
        ? 2500
        : 30_000,
  });

export const useReport = (key: ReportKey) =>
  useQuery({
    queryKey: ["report", key],
    queryFn: () => api<ReportSummary>(`/api/reports/${key}`),
    refetchInterval: (q) => (q.state.data?.current.status === "processing" ? 2500 : 30_000),
  });

export interface PeriodFilters {
  year?: number | null;
  sub?: number | null;
  status?: string | null;
  sort: string;
  page: number;
  page_size: number;
}

export const usePeriods = (key: ReportKey, f: PeriodFilters) =>
  useQuery({
    queryKey: ["periods", key, f],
    queryFn: () => api<PeriodsPage>(`/api/reports/${key}/periods${qs({ ...f })}`),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (hasProcessing(q.state.data?.items) ? 2500 : 30_000),
  });

export interface HistoryFilters {
  q?: string;
  report?: string | null;
  year?: number | null;
  sub?: string | null;
  status?: string | null;
  sort: string;
  page: number;
  page_size: number;
}

export const useHistory = (f: HistoryFilters) =>
  useQuery({
    queryKey: ["history", f],
    queryFn: () => api<Paged<Version>>(`/api/history${qs({ ...f })}`),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (hasProcessing(q.state.data?.items) ? 2500 : 30_000),
  });
