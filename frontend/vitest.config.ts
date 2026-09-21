import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    // Node by default: the pure logic under test has no DOM. Suites that need
    // one can opt in per file with a `// @vitest-environment jsdom` pragma.
    environment: "node",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
