import { useEffect, useState } from "react";
import type { MutableRefObject } from "react";
import type { SelectedUpdater, View } from "../../article/index.ts";
import { fetchBriefing } from "../api/briefingApi.ts";
import type { Briefing } from "../model/briefing.ts";

interface UseBriefingOptions {
  view: View;
  setSelected: (articleOrUpdater: SelectedUpdater) => void;
  isCompactRef: MutableRefObject<boolean>;
}

// 오늘의 AI 브리핑 로딩 상태. 브리핑 보기로 진입하거나 다시 시도할 때마다 새로 불러오며,
// 데스크톱이면 첫 브리핑 기사를 선택한다.
export default function useBriefing({ view, setSelected, isCompactRef }: UseBriefingOptions) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingLoading, setBriefingLoading] = useState(true);
  const [briefingError, setBriefingError] = useState("");
  const [briefingRetry, setBriefingRetry] = useState(0);

  useEffect(() => {
    if (view !== "briefing") return;
    const controller = new AbortController();
    setSelected(null);
    setBriefingLoading(true);
    setBriefingError("");
    fetchBriefing(controller.signal)
      .then((data) => {
        setBriefing(data);
        if (!isCompactRef.current && (data?.articles || []).length > 0) {
          setSelected(data.articles[0]);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setBriefingError("브리핑을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setBriefingLoading(false);
      });
    return () => controller.abort();
  }, [view, briefingRetry]);

  const retryBriefing = () => setBriefingRetry((n) => n + 1);

  return { briefing, briefingLoading, briefingError, retryBriefing };
}
