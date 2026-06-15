export function authLog(...args: unknown[]) {
  if (import.meta.env.DEV) {
    console.log("[Auth]", ...args);
  }
}
