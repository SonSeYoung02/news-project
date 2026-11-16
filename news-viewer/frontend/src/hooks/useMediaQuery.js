import { useEffect, useState } from "react";

// 미디어 쿼리 일치 여부를 반환한다. query와 onChange는 마운트 시점 값만 사용하므로
// onChange에는 setState처럼 렌더 간 동일한 함수만 사용한다.
export default function useMediaQuery(query, onChange) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const media = window.matchMedia(query);
    const handleChange = (event) => {
      setMatches(event.matches);
      onChange?.(event);
    };
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  return matches;
}
