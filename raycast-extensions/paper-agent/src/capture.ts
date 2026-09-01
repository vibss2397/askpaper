import { getSelectedText, getFrontmostApplication } from "@raycast/api";
import { runAppleScript } from "@raycast/utils";

export interface Source {
  app: string;
  title: string;
  url: string;
}

export async function captureContext(): Promise<{
  selectedText: string;
  raycastRawText: string;
  source: Source;
}> {
  let selectedText = "";
  let raycastRawText = "";
  try {
    raycastRawText = (await getSelectedText()).trim();
    selectedText = raycastRawText;
    console.log("Raycast selectedText:", JSON.stringify(raycastRawText));
  } catch (e) {
    console.log(
      "Raycast selectedText failed:",
      e instanceof Error ? e.message : e,
    );
  }

  let app = "";
  try {
    const front = await getFrontmostApplication();
    app = front.name;
    console.log("captureContext: frontmost app =", app);
  } catch {
    // Can't determine app
  }

  let source: Source = { app, title: "", url: "" };
  let chromeSource: Source | null = null;
  let safariSource: Source | null = null;

  // Chrome PDFs are not normal web pages: window.getSelection() usually can't
  // reach them, so only use browser fallbacks after Raycast's native capture.
  if (app === "Google Chrome" || (!selectedText && app !== "Safari")) {
    try {
      const [url, title] = await Promise.all([
        runAppleScript(
          'tell application "Google Chrome" to get URL of active tab of front window',
        ),
        runAppleScript(
          'tell application "Google Chrome" to get title of active tab of front window',
        ),
      ]);
      chromeSource = {
        app: "Google Chrome",
        title: title || "",
        url: url || "",
      };
      if (app === "Google Chrome") source = chromeSource;
    } catch {
      // AppleScript failed
    }

    if (!selectedText) {
      // First try JS selection (instant, works for regular web pages)
      try {
        const jsSelection = await runAppleScript(
          'tell application "Google Chrome" to execute front window\'s active tab javascript "window.getSelection().toString()"',
        );
        console.log("JS selection:", JSON.stringify(jsSelection));
        if (jsSelection && jsSelection.trim()) {
          selectedText = jsSelection.trim();
          source = chromeSource || { app: "Google Chrome", title: "", url: "" };
        }
      } catch (e) {
        console.log("JS selection failed:", e instanceof Error ? e.message : e);
      }
    }

    // If JS selection failed (e.g. PDF viewer), use clipboard.
    // Send Cmd+C directly to Chrome's process WITHOUT activating it —
    // Chrome's PDF viewer loses text selection when it loses focus.
    if (!selectedText) {
      try {
        console.log("Trying clipboard approach...");
        selectedText = await runAppleScript(`
          set the clipboard to ""
          tell application "System Events"
            tell process "Google Chrome"
              keystroke "c" using command down
            end tell
          end tell
          delay 0.3
          the clipboard as text
        `);
        console.log("Clipboard attempt 1:", JSON.stringify(selectedText));
        if (selectedText) selectedText = selectedText.trim();
        if (selectedText)
          source = chromeSource || { app: "Google Chrome", title: "", url: "" };
        if (!selectedText) {
          selectedText = await runAppleScript(`
            tell application "System Events"
              tell process "Google Chrome"
                keystroke "c" using command down
              end tell
            end tell
            delay 0.5
            the clipboard as text
          `);
          console.log("Clipboard attempt 2:", JSON.stringify(selectedText));
          if (selectedText) selectedText = selectedText.trim();
          if (selectedText)
            source = chromeSource || {
              app: "Google Chrome",
              title: "",
              url: "",
            };
        }
      } catch (e) {
        console.log(
          "Clipboard approach failed:",
          e instanceof Error ? e.message : e,
        );
      }
    }
  }

  if (app === "Safari" || (!selectedText && app !== "Google Chrome")) {
    try {
      const [url, title] = await Promise.all([
        runAppleScript(
          'tell application "Safari" to get URL of current tab of front window',
        ),
        runAppleScript(
          'tell application "Safari" to get name of current tab of front window',
        ),
      ]);
      safariSource = { app: "Safari", title: title || "", url: url || "" };
      if (app === "Safari") source = safariSource;
    } catch {
      // AppleScript failed
    }

    if (!selectedText) {
      // Try JS selection first
      try {
        const jsSelection = await runAppleScript(
          'tell application "Safari" to do JavaScript "window.getSelection().toString()" in front document',
        );
        if (jsSelection && jsSelection.trim()) {
          selectedText = jsSelection.trim();
          source = safariSource || { app: "Safari", title: "", url: "" };
        }
      } catch {
        // JS execution failed
      }
    }

    // Clipboard fallback — send Cmd+C to Safari process without activating
    if (!selectedText) {
      try {
        selectedText = await runAppleScript(`
          set the clipboard to ""
          tell application "System Events"
            tell process "Safari"
              keystroke "c" using command down
            end tell
          end tell
          delay 0.3
          the clipboard as text
        `);
        if (selectedText) selectedText = selectedText.trim();
        if (selectedText)
          source = safariSource || { app: "Safari", title: "", url: "" };
      } catch {
        // Keystroke simulation failed
      }
    }
  }

  return { selectedText, raycastRawText, source };
}
