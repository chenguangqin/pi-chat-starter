# Design System — common_agent

This is the cross-turn consistency anchor for the frontend build. Every component conforms to these tokens. The aesthetic is **"clean utility"** — a professional, minimal chat shell meant to be inherited by a platform engineer. No brand personality, no playful touches. Readable, structured, obvious.

---

## Palette

| Token | Value | Usage |
|---|---|---|
| `--bg-page` | `#FFFFFF` | Page background |
| `--bg-surface` | `#F9FAFB` | Sidebar, input area, empty states |
| `--bg-surface-hover` | `#F3F4F6` | Hover state on surface items |
| `--bg-surface-active` | `#EEF2FF` | Selected/active conversation in sidebar |
| `--bg-user-message` | `#EEF2FF` | User message bubble |
| `--bg-assistant-message` | `#FFFFFF` | Assistant message bubble |
| `--border-default` | `#E5E7EB` | Borders, dividers, assistant message bubble border |
| `--border-focus` | `#6366F1` | Focus rings |
| `--text-primary` | `#111827` | Body text, message content |
| `--text-secondary` | `#6B7280` | Timestamps, sidebar subtitles, placeholders |
| `--text-on-primary` | `#FFFFFF` | Text on primary-colored backgrounds |
| `--primary` | `#4F46E5` | Send button, active indicators, links |
| `--primary-hover` | `#4338CA` | Button hover |
| `--error` | `#DC2626` | Error messages, error state borders |
| `--error-bg` | `#FEF2F2` | Error message bubble background |

Tailwind mapping: `bg-white`, `bg-gray-50`, `bg-gray-100`, `bg-indigo-50`, `border-gray-200`, `text-gray-900`, `text-gray-500`, `bg-indigo-600`, `bg-indigo-700`, `text-red-600`, `bg-red-50`. Use Tailwind classes directly — no custom CSS variables needed unless the component requires runtime theming.

---

## Typography

| Token | Value | Tailwind | Usage |
|---|---|---|---|
| `--font-body` | `system-ui, -apple-system, sans-serif` | `font-sans` (Tailwind default) | All UI text |
| `--font-mono` | `'JetBrains Mono', 'Fira Code', ui-monospace, monospace` | `font-mono` | Code blocks in messages |
| `--text-body` | `15px / 1.6` | `text-[15px] leading-relaxed` | Message content |
| `--text-small` | `13px / 1.5` | `text-[13px] leading-normal` | Timestamps, metadata, sidebar items |
| `--text-heading` | `14px / 1.4, font-weight 600` | `text-sm font-semibold` | Section labels, sidebar header |
| `--text-input` | `15px / 1.5` | `text-[15px] leading-normal` | Message input textarea |

---

## Spacing

Base unit: **4px**. All spacing is a multiple.

| Token | Value | Tailwind | Usage |
|---|---|---|---|
| `--space-xs` | `4px` | `p-1` / `gap-1` | Tight inner padding |
| `--space-sm` | `8px` | `p-2` / `gap-2` | Between inline elements |
| `--space-md` | `12px` | `p-3` / `gap-3` | Component inner padding |
| `--space-lg` | `16px` | `p-4` / `gap-4` | Section padding, message bubble padding |
| `--space-xl` | `24px` | `p-6` / `gap-6` | Between major sections |
| `--space-2xl` | `32px` | `p-8` / `gap-8` | Page-level margins |

---

## Radius

| Token | Value | Tailwind | Usage |
|---|---|---|---|
| `--radius-sm` | `6px` | `rounded-md` | Buttons, inputs, small interactive elements |
| `--radius-md` | `12px` | `rounded-xl` | Message bubbles |
| `--radius-lg` | `16px` | `rounded-2xl` | Cards, modal panels (if any) |

---

## Elevation

Flat design — no box shadows on content. Only the input area gets a subtle top border to separate it from the message thread.

| Token | Usage |
|---|---|
| `border-t border-gray-200` | Input area separator |
| `border-r border-gray-200` | Sidebar right edge |

---

## Motion

| Token | Value | Tailwind | Usage |
|---|---|---|---|
| `--duration-fast` | `100ms` | `duration-100` | Hover color changes |
| `--duration-normal` | `150ms` | `duration-150` | Button press, focus ring |
| `--easing` | `ease-out` | `ease-out` | All transitions |

Keep motion minimal. No entrance animations on messages. No skeleton loaders. Streaming text appears character-by-character as it arrives — the real-time stream IS the animation.

---

## Component Patterns

### Sidebar (280px fixed)
- `bg-surface`, `border-r border-default`
- Header: app name in `--text-heading`, "New" button right-aligned
- Conversation items: `text-small`, single-line truncated title, hover → `bg-surface-hover`, active → `bg-surface-active` with left `border-l-2 border-primary`
- Items sorted by `updated_at` descending

### Message bubbles
- **User:** right-aligned, `bg-user-message`, `radius-md`, `text-body`, max-width 80%
- **Assistant:** left-aligned, `bg-assistant-message`, `border border-default`, `radius-md`, `text-body`, max-width 80%
- **Error:** left-aligned, `bg-error-bg`, `border border-error`, `radius-md`, `text-small`
- No avatars or icons — this is a shell, not a branded product

### Message input area
- Sticky bottom, `bg-surface`, `border-t border-default`
- Multi-line `<textarea>` with auto-grow (max 200px height), `radius-sm`, `border border-default`, `focus:border-focus focus:ring-1 focus:ring-focus`
- Send button: `bg-primary`, `text-on-primary`, `radius-sm`, disabled when empty or streaming
- Enter sends, Shift+Enter newline

### Streaming indicator
- While streaming: the send button shows a stop icon (square) and clicking it aborts
- No typing dots, no pulsing cursor — the arriving text IS the indicator
- After done: send button reverts to send icon

### Empty states
- No conversations: centered text "No conversations yet" + prominent "New conversation" button
- Empty conversation: centered text "Send a message to start"

---

## Do's and Don'ts

**Do:**
- Use Tailwind utility classes directly; don't create a CSS abstraction layer
- Keep the layout a simple two-column split (sidebar + main); no nested panels
- Let message content breathe — generous line-height (`leading-relaxed`) and padding
- Truncate long titles with `truncate`; never wrap in the sidebar
- Use `text-gray-500` for all secondary information — timestamps, metadata, placeholders
- Render markdown in assistant messages (bold, italic, code blocks, lists) — use a lightweight renderer

**Don't:**
- Don't add avatars, icons-in-circles, or decorative elements to messages
- Don't add animations beyond the streaming text itself
- Don't use shadows or gradients — the design is flat
- Don't add a dark mode — it's a v1 shell; dark mode is a later enhancement
- Don't use custom colors outside the palette above
- Don't add a top navbar or footer — the sidebar + main panel is the entire layout
- Don't make the sidebar collapsible — it's always visible at 280px
