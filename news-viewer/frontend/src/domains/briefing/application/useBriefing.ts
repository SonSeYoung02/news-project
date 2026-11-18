import { useEffect, useRef, useState } from "react";
import type { View } from "../../article/index.ts";
import { fetchBriefing } from "../api/briefingApi.ts";
import type { Briefing } from "../model/briefing.ts";

interface UseBriefingOptions {
  view: View;
}

// 오늘의 AI 브리핑 로딩 상태. 브리핑 보기로 진입하거나 다시 시도할 때마다 새로 불러온다.
export default function useBriefing({ view }: UseBriefingOptions) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingLoading, setBriefingLoading] = useState(view === "briefing");
  const [briefingError, setBriefingError] = useState("");
  const [briefingRetry, setBriefingRetry] = useState(0);
  const [briefingLoaded, setBriefingLoaded] = useState(false);
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (view !== "briefing") {
      reqIdRef.current += 1;
      setBriefing(null);
      setBriefingLoading(false);
      setBriefingError("");
      setBriefingLoaded(false);
      return;
    }

    const reqId = ++reqIdRef.current;
    const controller = new AbortController();
    setBriefingLoading(true);
    setBriefingError("");
    setBriefingLoaded(false);

    fetchBriefing(controller.signal)
      .then((data) => {
        if (reqIdRef.current !== reqId) return;
        setBriefing(data);
        setBriefingLoaded(true);
      })
      .catch(() => {
        if (!controller.signal.aborted && reqIdRef.current === reqId) {
          setBriefingError("브리핑을 불러오지 못했습니다.");
          setBriefingLoaded(true);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && reqIdRef.current === reqId) {
          setBriefingLoading(false);
        }
      });

    return () => controller.abort();
  }, [view, briefingRetry]);

  const retryBriefing = () => setBriefingRetry((n) => n + 1);

  const isBriefingLoading = view === "briefing" && (briefingLoading || !briefingLoaded);
  const isBriefingReady = view === "briefing" && !briefingLoading && briefingLoaded;

  return {
    briefing,
    briefingLoading: isBriefingLoading,
    briefingError,
    isBriefingReady,
    retryBriefing,
  };
}
