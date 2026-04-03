/**
 * System API Functions
 *
 * API calls for system-level configuration (prompts, settings).
 */

import { apiClient } from "./client";

/**
 * Fetch the standard prompt that is automatically submitted when a doctor
 * uploads their first scan in a new chat.
 */
export async function getAutoAnalysisPrompt(): Promise<string> {
  const { data } = await apiClient.get<{ prompt: string }>(
    "/api/system/auto-analysis-prompt"
  );
  return data.prompt;
}
