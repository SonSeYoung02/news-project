import { useEffect, useRef, useState } from "react";
import { fetchArticleById } from "../api/articleApi.ts";
import type { Article } from "../model/article.ts";
import { resolveArticleDetailError } from "../model/routeState.ts";

interface UseArticleDetailOptions {
  articleId: number | null;
  listArticles: Article[];
  listReady: boolean;
}

// URL의 :id가 현재 목록에 있으면 즉시 재사용하고, 없으면 GET /api/articles/{id} 로 단건 조회한다.
export function useArticleDetail({ articleId, listArticles, listReady }: UseArticleDetailOptions) {
  const [fetchedArticle, setFetchedArticle] = useState<Article | null>(null);
  const [fetchedId, setFetchedId] = useState<number | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const detailReqRef = useRef(0);

  const articleInList =
    articleId !== null && listReady
      ? (listArticles.find((item) => item.id === articleId) ?? null)
      : null;

  useEffect(() => {
    if (articleId === null) {
      detailReqRef.current += 1;
      setFetchedArticle(null);
      setFetchedId(null);
      setDetailLoading(false);
      setDetailError("");
      return;
    }

    if (!listReady) {
      return;
    }

    if (articleInList) {
      detailReqRef.current += 1;
      setFetchedArticle(null);
      setFetchedId(articleId);
      setDetailLoading(false);
      setDetailError("");
      return;
    }

    const reqId = ++detailReqRef.current;
    const controller = new AbortController();
    setFetchedArticle(null);
    setFetchedId(null);
    setDetailLoading(true);
    setDetailError("");

    fetchArticleById(articleId, controller.signal)
      .then((article) => {
        if (detailReqRef.current !== reqId) return;
        setFetchedArticle(article);
        setFetchedId(articleId);
        setDetailLoading(false);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted && detailReqRef.current === reqId) {
          setFetchedArticle(null);
          setFetchedId(articleId);
          setDetailError(resolveArticleDetailError(err));
          setDetailLoading(false);
        }
      });

    return () => controller.abort();
  }, [articleId, listReady, articleInList]);

  if (articleId === null) {
    return { selected: null, detailLoading: false, detailError: "" };
  }

  if (articleInList) {
    return { selected: articleInList, detailLoading: false, detailError: "" };
  }

  if (!listReady || fetchedId !== articleId) {
    return { selected: null, detailLoading: true, detailError: "" };
  }

  return {
    selected: fetchedArticle,
    detailLoading,
    detailError,
  };
}
