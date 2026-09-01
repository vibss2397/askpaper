import { launchCommand, LaunchType } from "@raycast/api";
import { captureContext, type Source } from "./capture";

export default async function Command() {
  const { selectedText, raycastRawText, source } = await captureContext();

  console.log("capture-and-ask: launching ask with", {
    selectedText: JSON.stringify(selectedText),
    source: JSON.stringify(source),
  });

  await launchCommand({
    name: "ask",
    type: LaunchType.UserInitiated,
    context: {
      selectedText,
      raycastRawText,
      source,
      invocationId: Date.now(),
    } satisfies AskLaunchContext,
  });
}

export type AskLaunchContext = {
  selectedText: string;
  raycastRawText: string;
  source: Source;
  invocationId: number;
};
