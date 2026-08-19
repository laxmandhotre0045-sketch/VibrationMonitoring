import React, { useState, useCallback } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Activity,
  AudioWaveform,
  Waves,
  Gauge,
  BellRing,
  HeartPulse,
  Eye,
  EyeOff,
  Loader2,
  AlertTriangle,
  Mail,
  Lock,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/ui/Toast";
import { LoginIntelligenceBg } from "@/components/brand/LoginIntelligenceBg";
import { cn } from "@/lib/utils";
import axios from "axios";

const FEATURES: { label: string; icon: LucideIcon }[] = [
  { label: "Real-Time Monitoring", icon: Activity },
  { label: "FFT Spectrum Analysis", icon: AudioWaveform },
  { label: "Time Waveform Analysis", icon: Waves },
  { label: "Predictive Maintenance", icon: Gauge },
  { label: "Anomaly Detection", icon: BellRing },
  { label: "Equipment Health Scoring", icon: HeartPulse },
];

const TAGLINE = "AI Powered Vibration Intelligence";

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function LoginPage() {
  const { login, isAuthenticated, isLoading, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockOn, setCapsLockOn] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  const returnUrl = (location.state as { from?: string } | null)?.from ?? "/";

  const checkCapsLock = useCallback((e: React.KeyboardEvent) => {
    setCapsLockOn(e.getModifierState("CapsLock"));
  }, []);

  const validate = (): boolean => {
    const errors: { email?: string; password?: string } = {};
    if (!email.trim()) errors.email = "Email is required";
    else if (!isValidEmail(email.trim())) errors.email = "Enter a valid email address";
    if (!password) errors.password = "Password is required";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      const me = await login(email.trim(), password);
      setPassword("");
      showToast("Welcome back! Signed in successfully.", "success");

      if (me.must_change_password) {
        navigate("/change-password", { replace: true });
      } else {
        navigate(returnUrl, { replace: true });
      }
    } catch (err) {
      setFailedAttempts((n) => n + 1);
      let message = "Sign in failed. Please check your credentials.";
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        if (typeof detail === "string") message = detail;
      }
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isLoading && isAuthenticated) {
    if (user?.must_change_password) {
      return <Navigate to="/change-password" replace />;
    }
    return <Navigate to={returnUrl} replace />;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#07111F]">
        <Loader2 size={32} className="text-[#FF6B00] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-[#07111F] text-white overflow-hidden">
      {/* Left panel — industrial brand + intelligence visuals */}
      <div className="relative flex flex-col px-g4 py-g5 sm:px-g5 sm:py-g6 lg:px-g6 lg:py-g6 lg:w-[61.8%] min-h-[360px] lg:min-h-screen lg:justify-center overflow-hidden">
        <LoginIntelligenceBg variant="left" />

        <div className="relative z-10 flex flex-col gap-g4 lg:gap-g4 max-w-xl">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <p className="text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-extrabold text-white tracking-tight leading-none mb-4">
              Sensovibe
            </p>

            <p className="text-base font-semibold text-[#FF6B00] tracking-wide mb-2">{TAGLINE}</p>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight mb-3 leading-tight">
              Intelligent Machine Health Monitoring
            </h1>
            <div className="brand-divider mb-3 max-w-[120px]" />
            <p className="text-sm sm:text-base text-white/85 max-w-lg leading-relaxed">
              Monitor machine vibration, equipment health, FFT analysis, and predictive
              maintenance from a single industrial platform.
            </p>
          </motion.div>

          <motion.div
            initial="hidden"
            animate="visible"
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.04 } },
            }}
            className="login-features-panel"
          >
            <p className="login-features-heading">Platform capabilities</p>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
              {FEATURES.map(({ label, icon: Icon }) => (
                <motion.li
                  key={label}
                  variants={{
                    hidden: { opacity: 0, y: 6 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  className="login-feature-item"
                >
                  <Icon size={17} className="text-[#FF6B00] shrink-0" strokeWidth={2.25} />
                  {label}
                </motion.li>
              ))}
            </ul>
          </motion.div>

          <p className="text-sm text-white/55 hidden lg:block">
            Sensovibe — Industrial Vibration Intelligence Platform
          </p>
        </div>
      </div>

      {/* Right panel — borderless login form */}
      <div className="relative flex-1 flex items-center justify-center lg:justify-start px-g4 py-g5 lg:py-g6 lg:pl-g6 lg:pr-g6">
        <LoginIntelligenceBg variant="right" />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.12 }}
          className="login-form-panel relative z-10 w-full max-w-[420px]"
        >
          <h2 className="login-form-heading">Welcome Back</h2>
          <p className="login-form-subtext">
            Sign in with your account to access the monitoring dashboard.
          </p>

          <form onSubmit={handleSubmit} className="login-form-fields" noValidate>
            <div className="login-form-group">
              <label htmlFor="email" className="login-form-label">
                Email *
              </label>
              <div
                className={cn(
                  "login-field-box",
                  fieldErrors.email && "login-field-box--error"
                )}
              >
                <span className="login-field-leading" aria-hidden>
                  <Mail size={20} />
                </span>
                <input
                  id="email"
                  type="text"
                  inputMode="email"
                  autoComplete="email"
                  spellCheck={false}
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setFieldErrors((f) => ({ ...f, email: undefined }));
                  }}
                  aria-invalid={!!fieldErrors.email}
                  className="login-field-input"
                  placeholder="you@company.com"
                />
                <span className="login-field-trailing" aria-hidden />
              </div>
              {fieldErrors.email && (
                <p className="login-form-error">{fieldErrors.email}</p>
              )}
            </div>

            <div className="login-form-group login-form-group--last">
              <label htmlFor="password" className="login-form-label">
                Password *
              </label>
              <div
                className={cn(
                  "login-field-box",
                  fieldErrors.password && "login-field-box--error"
                )}
              >
                <span className="login-field-leading" aria-hidden>
                  <Lock size={20} />
                </span>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setFieldErrors((f) => ({ ...f, password: undefined }));
                  }}
                  onKeyDown={checkCapsLock}
                  onKeyUp={checkCapsLock}
                  aria-invalid={!!fieldErrors.password}
                  className="login-field-input"
                  placeholder="Enter your password"
                />
                <span className="login-field-trailing">
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="login-field-toggle"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </span>
              </div>
              {fieldErrors.password && (
                <p className="login-form-error">{fieldErrors.password}</p>
              )}
              {capsLockOn && (
                <p className="login-form-warning">
                  <AlertTriangle size={14} />
                  Caps Lock is on
                </p>
              )}
            </div>

            {failedAttempts >= 5 && (
              <div className="login-form-alert login-form-alert--warning">
                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                <p>Multiple failed login attempts detected.</p>
              </div>
            )}

            {error && (
              <div role="alert" className="login-form-alert login-form-alert--error">
                {error}
              </div>
            )}

            <button type="submit" className="login-submit-btn" disabled={submitting}>
              {submitting ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 size={20} className="animate-spin" />
                  Signing in…
                </span>
              ) : (
                "Sign In"
              )}
            </button>
          </form>

          <p className="login-form-footer">
            Secure access for authorized facility staff only.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
