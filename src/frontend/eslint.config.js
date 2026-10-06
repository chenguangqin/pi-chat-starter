// ESLint flat config (ESLint 9). `npm run lint` runs this; `npm run typecheck` runs tsc
// — they catch different things and both are wired into `make lint`.
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "coverage"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      // Unused args are allowed when prefixed with _, which is the convention used for
      // ignored callback parameters in this codebase.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Test files run in jsdom but are driven by vitest globals-free imports; they also
    // legitimately use `any`-ish mock shapes.
    files: ["src/__tests__/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    // Config files are Node, not browser.
    files: ["*.config.{js,ts}", "vite.config.ts"],
    languageOptions: { globals: globals.node },
  },
);
