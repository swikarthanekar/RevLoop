import { describe, expect, it } from "vitest";

import { APP_NAME } from "@/lib/constants";

describe("constants", () => {
  it("exposes the RevLoop product name", () => {
    expect(APP_NAME).toBe("RevLoop");
  });
});
