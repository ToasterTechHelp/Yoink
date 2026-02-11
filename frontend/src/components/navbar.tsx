"use client";

import { useEffect, useMemo } from "react";
import Image from "next/image";
import Link from "next/link";
import { LogIn, LogOut } from "lucide-react";
import type { AuthChangeEvent, Session } from "@supabase/supabase-js";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { createClient } from "@/lib/supabase/client";
import { useYoinkStore } from "@/store/useYoinkStore";

export function Navbar() {
  const user = useYoinkStore((s) => s.user);
  const setUser = useYoinkStore((s) => s.setUser);
  const slotsUsed = useYoinkStore((s) => s.slotsUsed);

  const supabase = useMemo(() => createClient(), []);

  useEffect(() => {
    if (!supabase) return;

    const init = async () => {
      const { data } = await supabase.auth.getUser();
      setUser(data.user);
    };
    init();

    const { data: listener } = supabase.auth.onAuthStateChange(
      (_event: AuthChangeEvent, session: Session | null) => {
        setUser(session?.user ?? null);
      }
    );

    return () => listener.subscription.unsubscribe();
  }, [supabase, setUser]);

  const handleSignIn = async () => {
    if (!supabase) return;
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
  };

  const handleSignOut = async () => {
    if (!supabase) return;
    await supabase.auth.signOut();
    setUser(null);
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-14 items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="relative h-9 w-9">
            <Image
              src="/icon.svg"
              alt="Yoink logo"
              fill
              sizes="36px"
              priority
            />
          </div>
          <span className="text-lg font-bold tracking-tight">Yoink!</span>
        </Link>

        <div className="flex items-center gap-3">
          {user ? (
            <>
              <Badge variant="secondary" className="text-sm">
                {slotsUsed}/5
              </Badge>
              <span className="text-sm text-muted-foreground hidden sm:inline">
                Welcome back,{" "}
                <span className="font-medium text-foreground">
                  {user.user_metadata?.full_name?.split(" ")[0] ||
                    user.email?.split("@")[0]}
                </span>
              </span>
              <Button variant="ghost" size="sm" onClick={handleSignOut}>
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" onClick={handleSignIn}>
                Log in
              </Button>
              <Button size="sm" onClick={handleSignIn}>
                <LogIn className="mr-1 h-4 w-4" />
                Sign up
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
