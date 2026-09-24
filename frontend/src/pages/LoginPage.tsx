import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import type { AuthState } from "../hooks/useAuth";
import { CityEyeVisual, type EyePhase } from "../components/login/CityEyeVisual";
import { CityNetworkBackground } from "../components/login/CityNetworkBackground";
import { SecureLoginPanel } from "../components/login/SecureLoginPanel";
import { useCityEyeMotion, useReducedMotion } from "../components/login/useCityEyeMotion";
import "../login-awakens.css";

export function LoginPage({ auth }: { auth: AuthState }) {
  const [awakened, setAwakened] = useState(false);
  const [phase, setPhase] = useState<EyePhase>("idle");
  const [field, setField] = useState<"email" | "password" | "none">("none");
  const [engaged, setEngaged] = useState(false);
  const [pressed, setPressed] = useState(false);
  const [granted, setGranted] = useState(false);
  const attempting = useRef(false);
  const mounted = useRef(true);
  const reduced = useReducedMotion();
  const root = useCityEyeMotion(reduced);
  const location = useLocation();
  const navigate = useNavigate();
  const requested = (location.state as { from?: string } | null)?.from;
  const destination = auth.user?.role === "CITIZEN" ? "/citizen-map" : requested?.startsWith("/") && !requested.startsWith("//") && requested !== "/login" ? requested : "/command-center";

  useEffect(() => {
    const timer = window.setTimeout(() => setAwakened(true), 1700);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (phase === "success" && auth.user) {
      if (reduced) { navigate(destination, { replace: true }); return; }
      const message = window.setTimeout(() => setGranted(true), 260);
      const transition = window.setTimeout(() => navigate(destination, { replace: true }), 720);
      return () => { window.clearTimeout(message); window.clearTimeout(transition); };
    }
    if (phase === "failure") {
      const timer = window.setTimeout(() => setPhase("idle"), 1200);
      return () => window.clearTimeout(timer);
    }
  }, [phase, auth.user, destination, navigate, reduced]);

  async function submit(username: string, password: string) {
    if (attempting.current || auth.loading) return;
    attempting.current = true;
    setPhase("verifying");
    // The existing auth hook performs the real request immediately, unchanged.
    const success = await auth.login(username, password);
    if (!mounted.current) return;
    if (success) setPhase("success");
    else { attempting.current = false; setPhase("failure"); }
  }

  // Already-restored sessions skip the cinematic transition entirely.
  if ((auth.user && !attempting.current) || !auth.authRequired) return <Navigate to={destination} replace />;

  return <main ref={root} className="awaken-page" data-awake={awakened || reduced} data-phase={phase} data-field={field} data-engaged={engaged} data-pressed={pressed}>
    <div className="awaken-world"><CityNetworkBackground /></div>
    <section className="awaken-story" aria-label="CityEye municipal traffic intelligence">
      <header className="awaken-brand"><svg viewBox="0 0 42 30" aria-hidden="true"><path d="M2 15 12 5h18l10 10-10 10H12z"/><circle cx="21" cy="15" r="7"/><circle cx="21" cy="15" r="2"/></svg><strong>CITYEYE<span> AI</span></strong></header>
      <div className="awaken-editorial"><p className="awaken-kicker">Municipal traffic<br />intelligence</p><h1>THE<br />CITY<br />CAN<br />NOW<br /><span>SEE.</span></h1></div>
      <CityEyeVisual phase={phase} />
      <div className="awaken-caption"><span className="caption-rule" /><p>Turning existing city cameras into<br />real-time traffic intelligence.</p></div>
      <footer className="awaken-story-footer"><span>EXISTING CAMERAS. NEW PERSPECTIVE.</span><span>HUMAN-VERIFIED DECISIONS</span></footer>
    </section>
    <SecureLoginPanel auth={auth} phase={phase} granted={granted} onSubmit={(username,password) => void submit(username,password)} onFocusChange={setField} onEngage={setEngaged} onPress={setPressed} />
    <div className="awaken-transition" aria-hidden="true" />
  </main>;
}
