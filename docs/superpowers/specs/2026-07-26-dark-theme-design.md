# Dark Theme Design

## Goal

Make Paperplane use a polished dark theme by default while allowing users to switch to the existing light appearance.

## Scope

- Add an accessible light/dark toggle to the masthead.
- Keep dark as the initial theme for users without a saved preference.
- Persist an explicit preference in `localStorage` under the existing `paperplane:theme:v1` key.
- Apply the selected theme before hydration using the existing inline layout script to avoid a visible color flash.
- Convert hardcoded surface, border, text, status, and control colors to theme-aware CSS variables.
- Preserve the existing layout, typography, responsive behavior, and green/amber/red visual identity.

No system-preference detection, third-party theme package, or additional theme choices will be added.

## Components and Behavior

The home page owns the toggle state because it is the only current application screen. On mount, it reads the effective `data-theme` value placed on the document root by the layout. Activating the toggle switches between `dark` and `light`, updates `document.documentElement.dataset.theme`, and persists the value.

The toggle uses a native button with an explicit accessible label describing the action. Its icon reflects the destination theme, so a sun switches to light and a moon switches to dark.

The stylesheet keeps light values as the base variables and overrides them under `:root[data-theme="dark"]`. Component rules reference semantic variables rather than hardcoded light colors. Focus indicators and status colors retain sufficient contrast in both themes.

## Failure Handling

If browser storage is unavailable, theme switching still works for the current page. Storage reads and writes are guarded so privacy settings do not break rendering or interaction.

## Verification

- Component tests verify the default dark state, switching to light, switching back, the accessible label, and persistence.
- TypeScript, ESLint, Vitest, and the production Next.js build must pass.
- A manual browser check confirms the masthead, forms, job list, status panels, artifact links, errors, and responsive layout remain legible in both themes.

