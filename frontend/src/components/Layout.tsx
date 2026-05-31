import { Link, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  LayoutDashboard,
  Menu,
  Settings,
  ShieldCheck,
  Zap,
} from "lucide-react";
import clsx from "clsx";
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { FRONTEND_RELEASE_TAG, FRONTEND_VERSION } from "@/buildInfo";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const navigation = [
  { name: "Dashboard", href: "/app", icon: LayoutDashboard },
  { name: "Activities", href: "/app/activities", icon: Activity },
  { name: "Control Center", href: "/app/control-center", icon: ShieldCheck },
  { name: "Settings", href: "/app/settings", icon: Settings },
];

function ReleaseStatus() {
  const { data, isLoading } = useQuery({
    queryKey: ["service-health"],
    queryFn: api.getServiceHealth,
    staleTime: 60_000,
    refetchInterval: 120_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const apiVersion = String(data?.version || "").trim();
  const versionsAligned = Boolean(apiVersion) && apiVersion === FRONTEND_VERSION;

  let title = `UI ${FRONTEND_RELEASE_TAG}`;
  let detail = "API version unavailable";
  let toneClass = "text-[var(--ph-muted)]";

  if (isLoading) {
    detail = "Checking deployed backend version";
  } else if (apiVersion && versionsAligned) {
    title = `Release ${FRONTEND_RELEASE_TAG}`;
    detail = `API ${FRONTEND_RELEASE_TAG} aligned`;
    toneClass = "text-[var(--ph-success)]";
  } else if (apiVersion) {
    detail = `API v${apiVersion} differs from UI ${FRONTEND_RELEASE_TAG}`;
    toneClass = "text-[var(--ph-warning)]";
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--ph-muted)]">
          Release
        </span>
        <span className="text-xs font-semibold text-[var(--ph-text)]">{title}</span>
      </div>
      <p className={clsx("text-xs", toneClass)}>{detail}</p>
    </div>
  );
}

export default function Layout() {
  const location = useLocation();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [location.pathname]);

  const currentPageTitle =
    navigation.find((item) =>
      item.href === "/app"
        ? location.pathname === "/app" || location.pathname === "/app/"
        : location.pathname.startsWith(item.href),
    )?.name || "PipelineHealer";

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <div className="hidden border-r border-[var(--ph-border-subtle)] bg-[var(--ph-surface)] md:flex md:w-[248px] md:flex-col">
        <div className="flex min-h-0 flex-grow flex-col overflow-y-auto">
          <Link to="/" className="border-b border-[var(--ph-border-subtle)] px-5 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md border border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)]">
                <Zap className="h-5 w-5 text-[var(--ph-accent)]" />
              </div>
              <div>
                <div className="text-base font-semibold tracking-tight text-[var(--ph-text)]">
                  PipelineHealer
                </div>
                <div className="text-xs text-[var(--ph-muted)]">
                  Operator control plane
                </div>
              </div>
            </div>
          </Link>

          <div className="flex flex-1 flex-col px-4 py-5">
            <nav className="flex-1 space-y-1">
              {navigation.map((item) => {
                const isActive =
                  item.href === "/app"
                    ? location.pathname === "/app" ||
                      location.pathname === "/app/"
                    : location.pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={clsx(
                      isActive
                        ? "border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]"
                        : "border-transparent text-[var(--ph-muted)] hover:bg-[var(--ph-bg-elevated)] hover:text-[var(--ph-text)]",
                      "group flex items-center rounded-md border px-3 py-2.5 text-sm font-medium transition-colors",
                    )}
                  >
                    <item.icon
                      className={clsx(
                        isActive
                          ? "text-[var(--ph-accent)]"
                          : "text-[var(--ph-muted)] group-hover:text-[var(--ph-text)]",
                        "mr-3 flex-shrink-0 h-5 w-5",
                      )}
                    />
                    {item.name}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="border-t border-[var(--ph-border-subtle)] px-5 py-4">
            <p className="text-xs font-medium text-[var(--ph-text)]">
              OSS-first pipeline platform
            </p>
            <p className="mt-1 text-xs text-[var(--ph-muted)]">
              GitHub Actions and Jenkins bridge today.
            </p>
            <div className="mt-3 border-t border-[var(--ph-border-subtle)] pt-3">
              <ReleaseStatus />
            </div>
          </div>
        </div>
      </div>

      {/* Mobile header */}
      <div className="fixed left-0 right-0 top-0 z-20 flex h-14 items-center justify-between border-b border-[var(--ph-border-subtle)] bg-[var(--ph-surface)] px-3 pt-[env(safe-area-inset-top)] md:hidden">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            to="/"
            className="flex items-center gap-2 rounded-md px-1 py-0.5 hover:bg-[var(--ph-bg-elevated)]"
          >
            <Zap className="h-5 w-5 shrink-0 text-[var(--ph-accent)]" />
            <span className="text-sm font-semibold tracking-tight text-[var(--ph-text)]">
              PipelineHealer
            </span>
          </Link>
          <span className="truncate text-xs text-[var(--ph-muted)]">
            {currentPageTitle}
          </span>
        </div>

        <Sheet open={isMobileNavOpen} onOpenChange={setIsMobileNavOpen}>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open navigation menu"
              className="text-[var(--ph-text)] hover:bg-[var(--ph-bg-elevated)]"
            >
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-[var(--ph-accent)]" />
                PipelineHealer
              </SheetTitle>
              <SheetDescription>
                Navigate between dashboard, control center, activities, and
                settings.
              </SheetDescription>
            </SheetHeader>

            <nav className="space-y-1.5">
              {navigation.map((item) => {
                const isActive =
                  item.href === "/app"
                    ? location.pathname === "/app" ||
                      location.pathname === "/app/"
                    : location.pathname.startsWith(item.href);

                return (
                  <SheetClose asChild key={item.name}>
                    <Link
                      to={item.href}
                      className={clsx(
                        isActive
                          ? "border-[var(--ph-border-subtle)] bg-[var(--ph-bg-elevated)] text-[var(--ph-text)]"
                          : "border-transparent text-[var(--ph-muted)] hover:bg-[var(--ph-bg-elevated)] hover:text-[var(--ph-text)]",
                        "group flex items-center rounded-md border px-3 py-2.5 text-sm font-medium transition-colors",
                      )}
                    >
                      <item.icon
                        className={clsx(
                          isActive
                            ? "text-[var(--ph-accent)]"
                            : "text-[var(--ph-muted)] group-hover:text-[var(--ph-text)]",
                          "mr-3 h-5 w-5 shrink-0",
                        )}
                      />
                      {item.name}
                    </Link>
                  </SheetClose>
                );
              })}
            </nav>
            <div className="mt-6 border-t border-[var(--ph-border-subtle)] pt-4">
              <ReleaseStatus />
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Main content */}
      <div className="min-w-0 flex flex-col flex-1">
        <main className="flex-1 md:pt-0 pt-[calc(3.5rem+env(safe-area-inset-top))]">
          <div className="py-8">
            <div className="mx-auto max-w-[1440px] px-4 sm:px-6 md:px-8">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
