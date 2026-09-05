"use client";

/**
 * Last-resort boundary for a failure in the root layout itself.
 *
 * This replaces `<html>` wholesale, so it cannot use the app's providers,
 * fonts or Tailwind theme tokens — none of them are mounted at this point.
 * Colors are therefore inline and theme-neutral on purpose.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem",
          background: "#fafafa",
          color: "#171717",
          fontFamily:
            "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        }}
      >
        <div style={{ maxWidth: "28rem" }}>
          <p
            style={{
              margin: 0,
              fontSize: "0.75rem",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              color: "#525252",
            }}
          >
            RevLoop
          </p>
          <h1
            style={{
              margin: "0.5rem 0 0",
              fontSize: "1.5rem",
              fontWeight: 600,
            }}
          >
            RevLoop could not start
          </h1>
          <p style={{ marginTop: "0.5rem", fontSize: "0.875rem", color: "#525252" }}>
            Reload the page to try again.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: "1.5rem",
              padding: "0.5rem 0.75rem",
              borderRadius: "0.375rem",
              border: "none",
              background: "#171717",
              color: "#ffffff",
              fontSize: "0.875rem",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
          {error.digest ? (
            <p style={{ marginTop: "1.5rem", fontSize: "0.75rem", color: "#525252" }}>
              Reference: <code>{error.digest}</code>
            </p>
          ) : null}
        </div>
      </body>
    </html>
  );
}
