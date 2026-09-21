/**
 * Build-time feature flags, with a per-browser override for QA.
 *
 * Resolution order, first hit wins:
 *   1. `localStorage["ff:<name>"]` — "on" / "off". Survives reloads, scoped to
 *      one browser, so a tester can flip a flag on a deployed build without a
 *      rebuild or a backend change.
 *   2. `import.meta.env.VITE_<NAME>` — "true"/"1" or "false"/"0".
 *   3. The default below.
 *
 * Reading localStorage is wrapped: a browser with site data blocked throws on
 * access, and a flag lookup must never be the thing that breaks a page.
 */

export const FEATURE_FLAGS = {
  /**
   * The rebuilt 3D Digital Twin viewer — GLB models, studio lighting, x-ray,
   * HTML labels with leader lines.
   *
   * Defaults on in development and off in production builds, so the old viewer
   * stays the shipped one until this is signed off.
   */
  digitalTwinV2: {
    env: "VITE_DIGITAL_TWIN_V2",
    default: import.meta.env.DEV,
  },
} as const;

export type FeatureFlagName = keyof typeof FEATURE_FLAGS;

function readOverride(name: FeatureFlagName): boolean | null {
  try {
    const raw = window.localStorage.getItem(`ff:${name}`);
    if (raw === "on" || raw === "true" || raw === "1") return true;
    if (raw === "off" || raw === "false" || raw === "0") return false;
  } catch {
    // Site data blocked (private window, locked-down kiosk). Fall through.
  }
  return null;
}

function readEnv(key: string): boolean | null {
  const raw = (import.meta.env as Record<string, string | undefined>)[key];
  if (raw === undefined) return null;
  const value = raw.trim().toLowerCase();
  if (value === "true" || value === "1") return true;
  if (value === "false" || value === "0") return false;
  return null;
}

export function isFeatureEnabled(name: FeatureFlagName): boolean {
  const flag = FEATURE_FLAGS[name];
  return readOverride(name) ?? readEnv(flag.env) ?? flag.default;
}

/**
 * Flip a flag for this browser only. Pass `null` to drop back to the
 * environment default.
 *
 * Exposed on `window.__ff` in development so a flag can be toggled from the
 * console without digging through localStorage keys.
 */
export function setFeatureOverride(name: FeatureFlagName, value: boolean | null) {
  try {
    if (value === null) window.localStorage.removeItem(`ff:${name}`);
    else window.localStorage.setItem(`ff:${name}`, value ? "on" : "off");
  } catch {
    // Nothing useful to do — the caller asked for a preference, not a guarantee.
  }
}

if (import.meta.env.DEV && typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).__ff = {
    list: () =>
      Object.keys(FEATURE_FLAGS).reduce<Record<string, boolean>>((all, key) => {
        all[key] = isFeatureEnabled(key as FeatureFlagName);
        return all;
      }, {}),
    set: setFeatureOverride,
  };
}
