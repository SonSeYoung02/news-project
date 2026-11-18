import type { ArticleDto } from "../../article/index.ts";

// GET /briefing (BriefingResponse)
export interface BriefingResponseDto {
  generated_at: string;
  window_start: string;
  window_end: string;
  selection_method: string;
  articles?: ArticleDto[] | null;
}
