# Research Notes — alpha.15 AI Operator UI

## Problem

A decorative iframe would look convincing but can represent a different browsing context from the one Habitat's AI actually controls. Different origin, cookies, client-side memory, navigation timing, CSP/X-Frame-Options and browser process state can all make the iframe diverge from the agent's Playwright page.

## Decision

Use the actual Habitat Playwright page as the source of truth and expose an observer mirror:

- capture the viewport after open/observe/action;
- persist a stable per-session frame outside the browser thread;
- publish semantic target geometry with action events;
- animate the cursor in Observatory from normalized coordinates;
- use screenshot pixels only for human visibility, not for automated correctness claims.

## Why the cursor is event-driven

A full remote-desktop stream would add substantial transport, encoding, lifecycle and resource complexity. For Habitat's current semantic browser control, action-boundary frames plus the exact target rectangle preserve the important causal story: where the AI intended to act, what action it performed, and what browser state existed after the receipt.

The design can later evolve toward CDP screencast/WebRTC without changing the activity receipt contract.

## Privacy rule

Visible typing is useful for understanding search/filter/form actions, but persistence must not casually leak secrets. The first alpha.15 filter treats password and common credential/payment naming/autocomplete conventions as sensitive and stores only `[REDACTED]` plus length.

## UI direction

The visual language intentionally combines:

- a dark multicolor machine-world cockpit;
- glass browser chrome;
- semantic target brackets rather than arbitrary decorative crosshairs;
- an AI cursor with short action label;
- restrained scan/radar/telemetry effects;
- a split topology + software mode for simultaneous causal context.

The goal is “hacker workstation” energy while every bright visual still maps to an inspectable Habitat event or state.
