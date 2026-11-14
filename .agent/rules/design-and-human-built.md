# Design and Human-Built Rules for CRISIS AGENTS

These rules apply to every frontend step and component.

## Design Rules
- Mood: a quiet, serious operations console. Minimal, flat, dense but not crowded.
- Tailwind theme tokens only:
  - `bg`: `#0B0B0C` (page)
  - `surface`: `#111113` (panels)
  - `surface-2`: `#17171A` (raised elements, inputs)
  - `border`: `#26262B` (1px dividers)
  - `text`: `#F4F4F5` (primary)
  - `muted`: `#8B8B94` (secondary)
  - `accent`: `#E5484D` (the one red thing in an area)
  - `accent-dim`: `rgba(229,72,77,0.15)` (request tint)
  - `ok`: `#4ADE80` (verified / healthy only)
- No hex values inside components. Always use Tailwind tokens (`bg-surface`, `border-border`, etc.).
- Red is the only accent. Use it for the active agent, the current round, the primary action, and critical alerts. If everything is red, nothing is.
- No gradients, glassmorphism, glow, purple or blue. Status is text plus a small dot, never a large colored block.
- Font: `ui-sans-serif, system-ui, sans-serif`. Use `tabular-nums` on all numbers.
- Font sizes: 11 (uppercase tracked), 12, 13, 14, 16, 20, 28 only.
- Font weights: 400, 500, 600 only.
- 4px spacing grid. Radius 6px on panels (`rounded-panel`), 4px on controls (`rounded-control`). 1px borders instead of shadows. Panel padding 16 or 24px.
- Lucide icons at 16px, stroke 1.5. No emoji.

## Human-Built Rules
- No hero banners, floating blobs, fake 3D, sparkle icons, or "AI-powered" badges.
- Copy is plain and specific: "Grid supply dropped to 80 MW". No exclamation marks.
- Panels have uneven, realistic sizes. Not every card is the same.
- Every panel has real loading, empty, and error states. An empty state is one muted line.
- Formats are consistent: `120 MW`, `3 / 6 agents`, `14:32:07`.
- Components are small and named by job (`AgentCard`, `MessageBubble`). No giant files, commented-out code, or lorem ipsum.

## Motion Rules (functional only)
- 150-250ms, ease-out. No bounce or spring overshoot, and nothing loops.
- Chat message: fade in + 4px slide up.
- Requesting agent card: border animates to red and a faint tint holds ~3s, then fades.
- Network edge: stroke turns red, one dot travels the edge (~800ms), then fades to grey after ~2s.
- Number change: short cross-fade, no counting up.
- Allocation bars: 300ms width transition.
- Respect `prefers-reduced-motion`: drop the dot and slides, keep color changes.
- The page is calm at rest. Nothing animates unless something happened.

