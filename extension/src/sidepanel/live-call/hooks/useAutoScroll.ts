import { useRef, useEffect, useCallback } from "preact/hooks";
import { useSignal } from "@preact/signals";

interface AutoScrollResult {
  containerRef: { current: HTMLDivElement | null };
  isAtBottom: boolean;
  scrollToBottom: () => void;
}

export function useAutoScroll(deps: unknown[]): AutoScrollResult {
  const containerRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useSignal(true);

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      isAtBottom.value = true;
    }
  }, []);

  // Track scroll position
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleScroll = () => {
      const threshold = 40;
      isAtBottom.value =
        el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-scroll on new content
  useEffect(() => {
    if (isAtBottom.value) {
      scrollToBottom();
    }
  }, deps);

  return {
    containerRef,
    isAtBottom: isAtBottom.value,
    scrollToBottom,
  };
}
