/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        warm: "hsl(var(--warm))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          hover: "hsl(var(--primary-hover))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        surface: "hsl(var(--surface))",
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          dark: "hsl(var(--accent-dark))",
          deep: "hsl(var(--accent-deep))",
        },
        signal: {
          light: "#F5A623",
          dark: "#D98C00",
          deep: "#B86E00",
        },
        cta: {
          DEFAULT: "#FF6B00",
          hover: "#E55F00",
          foreground: "#FFFFFF",
        },
        page: {
          accent: "#FF6B00",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        brand: {
          DEFAULT: "#15366D",
          hover: "#1F3F78",
          accent: "#F5A623",
          "accent-dark": "#D98C00",
          "accent-deep": "#B86E00",
          warm: "#FFFDF8",
          sidebar: "#FFFDF8",
        },
        machine: {
          healthy: "#22C55E",
          warning: "#F5A623",
          critical: "#EF4444",
          offline: "#94A3B8",
        },
      },
      backgroundImage: {
        "signal-gradient": "linear-gradient(90deg, #F5A623 0%, #D98C00 100%)",
        "signal-gradient-v": "linear-gradient(180deg, #F5A623 0%, #D98C00 100%)",
        "signal-gradient-hover": "linear-gradient(90deg, #D98C00 0%, #B86E00 100%)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "0.75rem",
        "2xl": "1rem",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(21, 54, 109, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02)",
        "card-hover": "0 4px 16px rgba(21, 54, 109, 0.06), 0 2px 4px rgba(0, 0, 0, 0.03)",
        nav: "0 1px 0 rgba(21, 54, 109, 0.06)",
        logo: "0 2px 8px rgba(21, 54, 109, 0.06)",
        signal: "0 0 0 1px rgba(245, 166, 35, 0.25)",
        cta: "0 4px 14px rgba(255, 107, 0, 0.32)",
        "cta-hover": "0 6px 20px rgba(255, 107, 0, 0.4)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out forwards",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
