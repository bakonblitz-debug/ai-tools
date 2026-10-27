# Frontend standards

Drop-in for frontend work, shared across React, Vue, and any other UI framework. Extends `../coding-standards.md`; the universal floor still applies in full. This file adds what is specific to building interfaces. Framework-specific files (`react.md`, `vue.md`) can layer on top of this one when there is real content to add.

## Accessibility is a requirement, not a polish pass

- **WCAG 2.2 AA is the target**, treated the same way OWASP is on the security side: a working checklist, not a poster. Accessibility is on the same footing as validation and error handling in the universal floor, so it never gets simplified away to ship faster.
- **Semantic HTML first.** A `<button>` is a button, a `<nav>` is navigation, a heading is a real heading. The native element carries keyboard behaviour, focus, and screen-reader semantics for free. This is the native-platform rung of the ladder: I reach for a custom widget only when no native element does the job.
- **Everything works from the keyboard.** Every interactive element is reachable and operable by keyboard alone, focus order follows the visual order, and focus is never trapped. If I build a custom control, I own its ARIA roles, states, and key handling, and I test it without a mouse.
- **Labels and text alternatives.** Every form control has a programmatic label, every meaningful image has alt text, and decorative images are marked as such. Icon-only buttons get an accessible name.
- **Contrast and non-colour cues.** Text meets the AA contrast ratio, and colour is never the only signal for state (error, success, selected) since that fails for colour-blind and low-vision users.
- **Respect user settings.** Honour reduced-motion preferences and don't disable zoom or fix font sizes in a way that breaks reflow.

## Structure

- Prefer the framework's native primitives (`<input type="date">`, `<details>`, `<dialog>`) over reinvented components, per the ladder. Reach for a library only when the native element genuinely can't do the job.
- Keep components small with one reason to change, the SOLID single-responsibility rule applied to the component tree.
