import type { Article } from "../../article/index.ts";

export interface Briefing {
  generated_at: string;
  window_start: string;
  window_end: string;
  selection_method: string;
  articles: Article[];
}
