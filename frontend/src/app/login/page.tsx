"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { EyeOff, Building2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { useCompanyName } from "@/lib/public-settings";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const { setUser, setBootstrapped, user, hydrated } = useAuth();
  const companyName = useCompanyName();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const next = search.get("next") || "/dashboard";

  useEffect(() => {
    if (hydrated && user) {
      router.replace(next);
    }
  }, [hydrated, user, router, next]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const resp = await api.post("/auth/login", { username, password });
      setUser(resp.data.data.user);
      setBootstrapped(true);
      router.replace(next);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        "Sign in failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex font-sans bg-white">
      {/* Left Side - Hero Image */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-zinc-900 overflow-hidden">
        <img
          src="/hero-building.jpg"
          alt="Labor Camp"
          className="absolute inset-0 w-full h-full object-cover opacity-90"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent"></div>
        
        <div className="absolute bottom-16 left-16 right-16 text-white">
          <h2 className="text-4xl lg:text-5xl font-light tracking-tight mb-6 leading-tight">
            Redefining <br/><span className="font-semibold">Property Management</span>
          </h2>
          <p className="text-white/70 text-base max-w-md leading-relaxed font-light">
            Experience seamless control over your real estate portfolio with our next-generation platform designed for industry leaders.
          </p>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="w-full lg:w-1/2 flex flex-col items-center justify-center p-8 sm:p-12 lg:p-24 relative">
        
        <div className="w-full max-w-sm">
          <div className="flex items-center gap-3 mb-16">
            <div className="w-10 h-10 bg-zinc-950 rounded flex items-center justify-center text-white">
              <Building2 className="w-5 h-5 stroke-[1.5]" />
            </div>
            <span className="font-semibold text-xl tracking-tight text-zinc-950">{companyName}</span>
          </div>

          <h1 className="text-3xl font-semibold text-zinc-950 mb-2 tracking-tight">Sign In</h1>
          <p className="text-zinc-500 text-sm mb-12 font-light">Enter your credentials to access your account.</p>

          <form className="space-y-6" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest" htmlFor="username">
                Username or Email
              </label>
              <input
                id="username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full h-12 border-b border-zinc-200 bg-transparent px-0 text-zinc-950 text-base focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-300 rounded-none"
                placeholder="admin"
              />
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest" htmlFor="password">
                  Password
                </label>
                <a href="#" className="text-xs font-medium text-zinc-400 hover:text-zinc-900 transition-colors">
                  Forgot?
                </a>
              </div>
              <div className="relative">
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-12 border-b border-zinc-200 bg-transparent px-0 pr-10 text-zinc-950 text-base focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-300 rounded-none"
                  placeholder="••••••••"
                />
                <div className="absolute inset-y-0 right-0 flex items-center pointer-events-none">
                  <EyeOff className="h-4 w-4 text-zinc-300" />
                </div>
              </div>
            </div>

            <div className="flex items-center pt-2">
              <label className="flex items-center gap-3 cursor-pointer group">
                <div className="relative flex items-center justify-center w-5 h-5">
                  <input type="checkbox" className="peer appearance-none w-5 h-5 border border-zinc-300 rounded-sm checked:bg-zinc-950 checked:border-zinc-950 transition-all cursor-pointer" defaultChecked />
                  <svg className="absolute w-3 h-3 text-white pointer-events-none opacity-0 peer-checked:opacity-100" viewBox="0 0 14 10" fill="none">
                    <path d="M1 5L4.5 8.5L13 1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <span className="text-sm text-zinc-500 font-light group-hover:text-zinc-900 transition-colors">Keep me signed in</span>
              </label>
            </div>
            
            {error && (
              <div className="text-sm font-medium text-red-600 bg-red-50 p-4 border-l-4 border-red-500">
                {error}
              </div>
            )}

            <div className="pt-8">
              <button
                type="submit"
                disabled={busy}
                className="w-full h-14 bg-zinc-950 hover:bg-zinc-800 text-white font-medium tracking-wide transition-colors disabled:opacity-60 text-sm flex items-center justify-center gap-3"
              >
                {busy ? "Authenticating…" : "Sign In"}
                {!busy && <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>}
              </button>
            </div>
          </form>
        </div>
        
        {/* Footer items */}
        <div className="absolute bottom-8 right-8 lg:right-16 text-xs font-light text-zinc-400 flex gap-6">
          <a href="#" className="hover:text-zinc-900 transition-colors">Privacy</a>
          <a href="#" className="hover:text-zinc-900 transition-colors">Terms</a>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
