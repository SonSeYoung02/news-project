import { fetchJSON } from "../../../shared/api/client.ts";
import { toArticle } from "../../article/index.ts";
import type { Briefing } from "../model/briefing.ts";
import type { BriefingResponseDto } from "./types.ts";

export function toBriefing(dto: BriefingResponseDto): Briefing {
  return {
    generated_at: dto.generated_at,
    window_start: dto.window_start,
    window_end: dto.window_end,
    selection_method: dto.selection_method,
    articles: Array.isArray(dto.articles) ? dto.articles.map(toArticle) : [],
  };
}

export async function fetchBriefing(signal?: AbortSignal): Promise<Briefing> {
  const dto = await fetchJSON<BriefingResponseDto>("/briefing", signal);
  return toBriefing(dto);
}
