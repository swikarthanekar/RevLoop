import { configure } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/**
 * Testing Library's default `findBy*` timeout is 1000ms, measured in wall
 * clock. That is ample for a single file but not for the whole suite: 25 files
 * run in parallel workers on a shared CPU, so a component whose data arrives in
 * one microtask can still take over a second of wall time to settle under load.
 *
 * The result was a suite that passed in isolation and failed intermittently in
 * full runs -- three consecutive runs gave 335, 334 and 333 passes, always with
 * "Unable to find role=row", always in whichever file happened to be starved.
 *
 * Raising the budget removes the starvation flake without weakening any
 * assertion: a genuinely broken component never renders the queried element, so
 * it still fails, just after a longer wait.
 */
configure({ asyncUtilTimeout: 5000 });
