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
    <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 bg-white font-sans">
      {/* Left Column (Image & Marketing) */}
      <div className="hidden md:flex flex-col items-center justify-center p-8 lg:p-16 relative border-r border-slate-100">
        <div className="absolute top-8 left-8 flex items-center gap-2">
          {/* Logo Placeholder */}
          <div className="w-8 h-8 bg-indigo-500 rounded flex items-center justify-center text-white font-bold text-lg">
            <Building2 className="w-5 h-5" />
          </div>
          <span className="font-bold text-xl tracking-tight text-slate-900">{companyName}</span>
        </div>
        
        <div className="relative w-full max-w-sm mb-12">
          {/* Arch Image */}
          <div className="relative rounded-t-full overflow-hidden border-[6px] border-indigo-50/50 aspect-[3/4] bg-slate-100 shadow-sm">
            {/* Using an Unsplash placeholder for the modern house architecture */}
            <img 
              src="https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=80" 
              alt="Modern House" 
              className="w-full h-full object-cover" 
            />
          </div>
          
          {/* Floating Card */}
          <div className="absolute -left-12 bottom-12 bg-white rounded-xl shadow-xl p-4 w-52 border border-slate-100 animate-fade-in">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-6 h-6 bg-yellow-100 rounded flex items-center justify-center text-yellow-600 text-xs">
                🏢
              </div>
              <span className="text-[11px] font-semibold text-slate-700">Property Rent</span>
            </div>
            <div className="text-2xl font-bold text-slate-900">5,450</div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] text-red-500 flex items-center font-medium">▼ -12.08%</span>
              {/* tiny line chart placeholder using SVG */}
              <svg width="40" height="15" viewBox="0 0 40 15" className="opacity-80">
                <path d="M0,15 L5,10 L10,12 L15,5 L20,8 L25,2 L30,6 L35,0 L40,4" fill="none" stroke="#6366f1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M0,15 L5,10 L10,12 L15,5 L20,8 L25,2 L30,6 L35,0 L40,4 L40,15 Z" fill="url(#grad)" opacity="0.2"/>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#ffffff" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
          </div>
        </div>
        
        <div className="text-center max-w-md">
          <h2 className="text-[28px] font-bold text-slate-900 mb-4 leading-[1.2] tracking-tight">
            Discover Your Dream Property<br/>and Navigate the Market
          </h2>
          <p className="text-slate-500 text-sm mb-8 leading-relaxed max-w-[90%] mx-auto font-medium">
            Transform your real estate search with our smart dashboard—find the perfect property and stay ahead of trends.
          </p>
          {/* Dots */}
          <div className="flex justify-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-slate-200"></div>
            <div className="w-2 h-2 rounded-full bg-indigo-500 ring-[3px] ring-indigo-50 relative -top-[1px]"></div>
            <div className="w-1.5 h-1.5 rounded-full bg-slate-200"></div>
            <div className="w-1.5 h-1.5 rounded-full bg-slate-200"></div>
          </div>
        </div>
      </div>

      {/* Right Column (Login Form) */}
      <div className="flex flex-col justify-center p-8 lg:p-24 relative bg-white">
        <div className="w-full max-w-sm mx-auto">
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Welcome Back to {companyName}!</h1>
          <p className="text-slate-500 text-sm mb-10 font-medium">Sign in your account</p>

          <form className="space-y-6" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-600 block" htmlFor="username">
                Your Email
              </label>
              <input
                id="username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full h-11 rounded-lg border border-indigo-200 bg-white px-3 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all placeholder:text-slate-300 font-medium shadow-[0_0_0_2px_rgba(99,102,241,0.05)]"
                placeholder="albert45@mail.com"
              />
            </div>
            
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-600 block" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-11 rounded-lg border border-slate-200 bg-white px-3 pr-10 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all placeholder:text-slate-400 font-medium"
                  placeholder="••••••••"
                />
                <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                  <EyeOff className="h-4 w-4 text-slate-400" />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer group">
                <input type="checkbox" className="w-4 h-4 rounded text-indigo-500 border-slate-300 focus:ring-indigo-500 cursor-pointer" defaultChecked />
                <span className="text-xs text-slate-600 font-semibold group-hover:text-slate-900 transition-colors">Remember Me</span>
              </label>
              <a href="#" className="text-xs font-semibold text-slate-400 hover:text-indigo-500 transition-colors">
                Forgot Password?
              </a>
            </div>
            
            {error && (
              <div className="text-sm font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-center">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full h-11 rounded-lg bg-[#765bf5] hover:bg-[#684be3] text-white font-semibold transition-colors disabled:opacity-60 text-sm shadow-sm"
            >
              {busy ? "Signing in…" : "Login"}
            </button>

            <div className="relative flex items-center py-2">
              <div className="flex-grow border-t border-slate-100"></div>
              <span className="flex-shrink-0 mx-4 text-slate-400 text-[11px] font-medium">Or</span>
              <div className="flex-grow border-t border-slate-100"></div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <button type="button" className="h-10 flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors text-slate-600 font-semibold text-xs shadow-sm">
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" className="w-4 h-4" alt="Google" />
                Continue with Google
              </button>
              <button type="button" className="h-10 flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors text-slate-600 font-semibold text-xs shadow-sm">
                <svg className="w-4 h-4 fill-slate-900" viewBox="0 0 24 24"><path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.09 2.31-.86 3.63-.72 1.34.1 2.39.63 3.05 1.54-2.73 1.57-2.28 5.37.5 6.44-.65 1.83-1.46 3.8-2.26 4.91zm-4.75-13.62c-.17-2.61 2.33-4.82 4.88-4.66.27 2.76-2.63 4.91-4.88 4.66z"/></svg>
                Continue with Apple
              </button>
            </div>

            <p className="text-center text-xs text-slate-500 font-medium pt-4">
              Don't have any account? <a href="#" className="text-[#765bf5] hover:underline font-bold">Sign up</a>
            </p>

            <p className="text-center text-xs text-slate-400 mt-2 font-medium">
              Default admin: <span className="text-slate-500">admin</span>
            </p>

          </form>
        </div>
        
        {/* Footer items */}
        <div className="absolute bottom-6 left-8 hidden md:block">
          <a href="#" className="text-xs text-slate-400 hover:text-slate-600 font-medium">Privacy Policy</a>
        </div>
        <div className="absolute bottom-6 right-8 hidden md:block">
          <span className="text-xs text-slate-400 font-medium">Copyright 2024</span>
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
