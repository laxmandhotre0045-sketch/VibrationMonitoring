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
        "helper-foreground": "hsl(var(--helper-foreground))",
        placeholder: "hsl(var(--placeholder-foreground))",
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
      /**
       * Spacing ladder — Fibonacci, which converges on the golden ratio.
       *
       * 4, 8, 13, 21, 34, 55: each step is the sum of the two before it, so
       * consecutive steps sit at 1.625, 1.615, 1.619... of each other. That is
       * the golden ratio arriving on whole pixels, which a phi-multiplied
       * ladder (16, 25.9, 41.9) never does.
       *
       * The rungs have jobs, and mixing them is what made the old layout feel
       * arbitrary:
       *   g1  4px  — icon-to-label, badge insets
       *   g2  8px  — related controls on one row
       *   g3 13px  — gap between sibling cards in a grid
       *   g4 21px  — padding inside a card
       *   g5 34px  — gap between page sections
       *   g6 55px  — page top/bottom breathing room
       */
      spacing: {
        g1: "0.25rem",
        g2: "0.5rem",
        g3: "0.8125rem",
        g4: "1.3125rem",
        g5: "2.125rem",
        g6: "3.4375rem",
      },
      maxWidth: {
        /* Content stops here so a 2560px monitor does not stretch a four-up
           KPI row into four near-empty 600px cards. */
        content: "1440px",
        "content-wide": "1760px",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      /**
       * Type scale — golden ratio, cube-root stepped.
       *
       * Ratio is phi^(1/3) = 1.1740, so every THIRD step is exactly a golden
       * jump: base(15) -> 2xl(24) -> ~5xl(38.5) is 1:phi:phi^2. A full phi
       * between adjacent sizes is far too violent for UI, but a third of one
       * gives a ramp that still resolves to golden proportions at the
       * distances that read as hierarchy — body to section title, section
       * title to page title.
       *
       * Below base the ratio halves to phi^(1/6) = 1.0844. Small text needs
       * finer steps: at 12-15px a full 1.174 jump crosses the legibility floor
       * in one move, and captions end up either shouting or unreadable.
       *
       * Sizes are in rem against a 16px root, which is why the values look
       * unround. They are meant to be read as the px comments.
       */
      fontSize: {
        xs: ["0.78125rem", { lineHeight: "1.125rem" }],   /* 12.5 / 18   */
        sm: ["0.859375rem", { lineHeight: "1.25rem" }],   /* 13.75 / 20  */
        base: ["0.9375rem", { lineHeight: "1.4375rem" }], /* 15 / 23     */
        lg: ["1.09375rem", { lineHeight: "1.625rem" }],   /* 17.5 / 26   */
        xl: ["1.28125rem", { lineHeight: "1.8125rem" }],  /* 20.5 / 29   */
        "2xl": ["1.5rem", { lineHeight: "2rem" }],        /* 24 / 32     */
        "3xl": ["1.75rem", { lineHeight: "2.25rem" }],    /* 28 / 36     */
        "4xl": ["2.0625rem", { lineHeight: "2.5rem" }],   /* 33 / 40     */
        "5xl": ["2.40625rem", { lineHeight: "1.15" }],    /* 38.5        */
        overline: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.06em", fontWeight: "600" }],
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
